"use client";
import { useRef, useState } from "react";
import { Shell } from "../../components/Shell";
import { Act, Status, useApi } from "../../components/ui";
import { api, API_BASE, session } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import { formatDateTime, formatNumber, formatBytes } from "../../lib/format";

export default function Files() {
  const { t, locale } = useI18n();
  const [trail, setTrail] = useState<{ id: string | null; name: string }[]>([{ id: null, name: "Files" }]);
  const [trashed, setTrashed] = useState(false);
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("name");
  const cur = trail[trail.length - 1].id;
  const d = useApi<any[]>("/v1/files", { parent_id: cur ?? undefined, trashed, q: q || undefined, sort });
  const caps = useApi<any>("/v1/files/handlers");
  const input = useRef<HTMLInputElement>(null);
  const archive = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<{ name: string; text?: string; img?: string } | null>(null);

  const upload = async (files: FileList | null, path = "/v1/files/upload") => {
    for (const f of Array.from(files ?? [])) {
      const fd = new FormData(); fd.append("file", f);
      await api(path, { form: fd, query: { parent_id: cur ?? undefined } });
    }
    d.reload();
  };
  const download = async (id: string, name: string, suffix = "download") => {
    const r = await fetch(`${API_BASE}/v1/files/${id}/${suffix}`, { headers: { Authorization: `Bearer ${session.token()}`,
      "X-Tenant-Id": session.tenant() ?? "" } });
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a"); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
  };
  const can = (mime: string, what: "preview" | "edit") => (caps.data?.handlers[mime] ?? caps.data?.default)?.[what];
  return (
    <Shell>
      <h1>{t("nav.files")}</h1>
      <nav aria-label={t("ui.folder_path")} className="row">{trail.map((c, i) =>
        <button key={i} onClick={() => setTrail(trail.slice(0, i + 1))} aria-current={i === trail.length - 1 ? "page" : undefined}>{c.name}</button>)}</nav>
      <div className="row" style={{ margin: "1rem 0" }}>
        <button onClick={() => input.current?.click()}>{t("files.upload")}</button>
        <input ref={input} type="file" multiple hidden onChange={(e) => upload(e.target.files)} />
        <button onClick={() => archive.current?.click()}>{t("ui.import_zip_or_tar")}</button>
        <input ref={archive} type="file" accept=".zip,.tar,.gz,.tgz" hidden onChange={(e) => upload(e.target.files, "/v1/files/import")} />
        <Act label={t("files.new_folder")} run={async () => { const name = window.prompt("Folder name"); if (name) await api("/v1/files/folders", { body: { name, parent_id: cur } }); }} onDone={d.reload} />
        <label style={{ margin: 0 }}>{t("common.search")}<input value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <label style={{ margin: 0 }}>{t("ui.sort")}<select value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="name">{t("ui.name")}</option><option value="updated_at">{t("ui.last_changed")}</option><option value="size_bytes">{t("ui.size")}</option></select></label>
        <label style={{ margin: 0, display: "flex", gap: ".4rem" }}><input type="checkbox" checked={trashed} onChange={(e) => setTrashed(e.target.checked)} />{t("ui.trash")}</label>
      </div>
      <Status error={d.error} loading={!d.data} />
      <table><thead><tr><th>{t("ui.name")}</th><th>{t("ui.type")}</th><th>{t("ui.size")}</th><th>{t("ui.changed")}</th><th>{t("ui.actions")}</th></tr></thead>
        <tbody>{(d.data ?? []).map((n) => <tr key={n.id}>
          <td>{n.kind === "dir" && !trashed ? <button onClick={() => setTrail([...trail, { id: n.id, name: n.name }])}>{n.name}/</button> : n.name}</td>
          <td>{n.kind === "dir" ? "Folder" : n.mime}</td><td>{n.size_bytes != null ? formatBytes(n.size_bytes, locale) : ""}</td>
          <td>{formatDateTime(n.updated_at, locale)}</td>
          <td className="row">{trashed ? <Act label={t("files.restore")} run={() => api(`/v1/files/${n.id}/restore`, { method: "POST" })} onDone={d.reload} /> : <>
            {n.kind === "file" && <button onClick={() => download(n.id, n.name)}>{t("files.download")}</button>}
            {n.kind === "dir" && <button onClick={() => download(n.id, `${n.name}.zip`, "export?fmt=zip")}>{t("common.export")}</button>}
            {n.kind === "file" && can(n.mime, "preview") && <button onClick={async () => {
              if (n.mime.startsWith("image/")) {
                const r = await fetch(`${API_BASE}/v1/files/${n.id}/preview`, { headers: { Authorization: `Bearer ${session.token()}`, "X-Tenant-Id": session.tenant() ?? "" } });
                setPreview({ name: n.name, img: URL.createObjectURL(await r.blob()) });
              } else setPreview({ name: n.name, text: (await api(`/v1/files/${n.id}/preview`)).text });
            }}>{t("ui.preview")}</button>}
            <Act label={t("files.rename")} run={async () => { const name = window.prompt("New name", n.name); if (name) await api(`/v1/files/${n.id}`, { method: "PATCH", body: { name } }); }} onDone={d.reload} />
            <Act label={t("files.copy")} run={() => api(`/v1/files/${n.id}/copy`, { body: { target_parent_id: cur } })} onDone={d.reload} />
            <Act label={t("files.trash")} run={() => api(`/v1/files/${n.id}`, { method: "DELETE" })} onDone={d.reload} />
          </>}</td></tr>)}</tbody></table>
      {preview && <section aria-label={`Preview of ${preview.name}`} className="banner">
        <div className="row"><strong>{preview.name}</strong><button onClick={() => setPreview(null)}>{t("ui.close")}</button></div>
        {preview.img ? <img src={preview.img} alt={preview.name} style={{ maxWidth: "100%" }} /> : <pre style={{ whiteSpace: "pre-wrap" }}>{preview.text}</pre>}
      </section>}
      <p className="lede">{t("ui.every_upload_is_checked_for_malware")}</p>
    </Shell>);
}
