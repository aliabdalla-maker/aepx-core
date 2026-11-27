// AavEndpointSecurity — Agentic Antivirus Endpoint Security client (register B-04 macOS, AV-01, VIS-01).
//
// Subscribes to ES_EVENT_TYPE_AUTH_OPEN and ES_EVENT_TYPE_AUTH_EXEC. For each event it asks the agent over the
// Unix socket /var/run/aav-verdict.sock (one JSON line per request, see aav_agent/realtime.py VerdictSocketServer)
// and answers the kernel before the message deadline. Fail-open: no agent, a slow reply or any error allows the
// operation, so a stopped agent never blocks the Mac. The agent's own executable is muted so its scanning reads
// never come back as events.
//
// Runs as a root LaunchDaemon (or inside a system extension). It needs the
// com.apple.developer.endpoint-security.client entitlement (granted by Apple), notarisation, and Full Disk Access.
// Build: kernel/macos/build.sh.
import EndpointSecurity
import Foundation

let socketPath = ProcessInfo.processInfo.environment["AAV_VERDICT_SOCKET"] ?? "/var/run/aav-verdict.sock"
let agentPath = ProcessInfo.processInfo.environment["AAV_AGENT_PATH"]
    ?? "/Library/Application Support/AgenticAntivirus/aav-agent"
let safetyMargin: UInt64 = 200_000_000      // answer at least 200 ms before the kernel deadline
let maxWait: UInt64 = 2_000_000_000         // and never wait more than 2 s

final class VerdictClient {
    private var fd: Int32 = -1
    private let lock = NSLock()

    private func connect() -> Bool {
        if fd >= 0 { return true }
        let s = socket(AF_UNIX, SOCK_STREAM, 0)
        if s < 0 { return false }
        var addr = sockaddr_un()
        addr.sun_family = sa_family_t(AF_UNIX)
        let maxLen = MemoryLayout.size(ofValue: addr.sun_path)
        _ = withUnsafeMutablePointer(to: &addr.sun_path) { ptr in
            ptr.withMemoryRebound(to: CChar.self, capacity: maxLen) { strncpy($0, socketPath, maxLen - 1) }
        }
        let ok = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.connect(s, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) == 0
            }
        }
        if !ok { close(s); return false }
        fd = s
        return true
    }

    private func reset() { if fd >= 0 { close(fd) }; fd = -1 }

    /// Returns true to allow. Any failure or timeout returns true (fail open).
    func allow(path: String, pid: pid_t, op: String, timeoutNs: UInt64) -> Bool {
        lock.lock(); defer { lock.unlock() }
        guard connect() else { return true }
        var tv = timeval(tv_sec: Int(timeoutNs / 1_000_000_000), tv_usec: Int32((timeoutNs % 1_000_000_000) / 1000))
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, socklen_t(MemoryLayout<timeval>.size))
        guard let body = try? JSONSerialization.data(withJSONObject: ["path": path, "pid": pid, "op": op]) else {
            return true
        }
        var line = body; line.append(0x0A)
        let sent = line.withUnsafeBytes { write(fd, $0.baseAddress, line.count) }
        if sent != line.count { reset(); return true }
        var reply = Data()
        var byte: UInt8 = 0
        while reply.count < 4096 {
            let n = read(fd, &byte, 1)
            if n != 1 { reset(); return true }
            if byte == 0x0A { break }
            reply.append(byte)
        }
        guard let obj = try? JSONSerialization.jsonObject(with: reply) as? [String: Any],
              let allow = obj["allow"] as? Bool else { return true }
        return allow
    }
}

let verdicts = VerdictClient()
let queue = DispatchQueue(label: "aav.es.verdicts", attributes: .concurrent)

func remainingNs(_ msg: UnsafePointer<es_message_t>) -> UInt64 {
    var info = mach_timebase_info_data_t()
    mach_timebase_info(&info)
    let now = mach_absolute_time()
    guard msg.pointee.deadline > now else { return 0 }
    let ns = (msg.pointee.deadline - now) * UInt64(info.numer) / UInt64(info.denom)
    return ns > safetyMargin ? min(ns - safetyMargin, maxWait) : 0
}

func path(of file: UnsafeMutablePointer<es_file_t>) -> String {
    let token = file.pointee.path          // es_string_token_t: length-delimited, not always NUL-terminated
    guard let data = token.data else { return "" }
    let bytes = UnsafeRawBufferPointer(start: UnsafeRawPointer(data), count: token.length)
    return String(decoding: bytes, as: UTF8.self)
}

var client: OpaquePointer?
let result = es_new_client(&client) { c, msg in
    es_retain_message(msg)
    queue.async {
        defer { es_release_message(msg) }
        let pid = msg.pointee.process.pointee.ppid          // reported for context only
        let budget = remainingNs(msg)
        switch msg.pointee.event_type {
        case ES_EVENT_TYPE_AUTH_EXEC:
            let target = path(of: msg.pointee.event.exec.target.pointee.executable)
            let ok = budget == 0 || verdicts.allow(path: target, pid: pid, op: "exec", timeoutNs: budget)
            es_respond_auth_result(c, msg, ok ? ES_AUTH_RESULT_ALLOW : ES_AUTH_RESULT_DENY, true)
        case ES_EVENT_TYPE_AUTH_OPEN:
            let target = path(of: msg.pointee.event.open.file)
            let ok = budget == 0 || verdicts.allow(path: target, pid: pid, op: "open", timeoutNs: budget)
            // Deny = no flags authorised; allow = every requested flag. Cache only allows.
            es_respond_flags_result(c, msg, ok ? 0xffff_ffff : 0, ok)
        default:
            es_respond_auth_result(c, msg, ES_AUTH_RESULT_ALLOW, false)
        }
    }
}

guard result == ES_NEW_CLIENT_RESULT_SUCCESS, let es = client else {
    FileHandle.standardError.write("es_new_client failed: \(result.rawValue) (entitlement, root and Full Disk Access needed)\n"
        .data(using: .utf8)!)
    exit(1)
}
es_mute_path(es, agentPath, ES_MUTE_PATH_TYPE_LITERAL)
es_mute_path(es, CommandLine.arguments[0], ES_MUTE_PATH_TYPE_LITERAL)
var events = [ES_EVENT_TYPE_AUTH_EXEC, ES_EVENT_TYPE_AUTH_OPEN]
guard es_subscribe(es, &events, UInt32(events.count)) == ES_RETURN_SUCCESS else {
    FileHandle.standardError.write("es_subscribe failed\n".data(using: .utf8)!)
    exit(1)
}
print("AavEndpointSecurity: protecting (verdicts from \(socketPath))")
dispatchMain()
