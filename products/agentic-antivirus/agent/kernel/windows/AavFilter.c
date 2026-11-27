/*
 * AavFilter — Agentic Antivirus file-system minifilter (register B-01 Windows, AV-01, VIS-01).
 *
 * Holds IRP_MJ_CREATE for existing files opened for read or execute by user-mode processes other than the agent,
 * asks the agent over the filter communication port \AavFilterPort (AavProtocol.h) and fails the open with
 * STATUS_ACCESS_DENIED when the agent answers "deny". Fail-open by design: no agent connected, a timeout
 * (AAV_REPLY_TIMEOUT), or any error lets the open proceed, and the agent's user-mode scanner still covers the file.
 *
 * Only one client may connect (the agent service, running as LocalSystem; the port's security descriptor allows
 * administrators and SYSTEM only). Opens made by the connected agent process are never held, so the agent can read
 * files to scan them without recursion.
 *
 * Production loading needs an allocated altitude in the FSFilter Anti-Virus group (320000-329999; the INF uses a
 * placeholder) and Microsoft attestation signing through Partner Center (EV certificate). Build: build.ps1.
 */
#include <fltKernel.h>
#include <ntstrsafe.h>
#include "AavProtocol.h"

#define AAV_POOL_TAG 'fvaA'
#define AAV_REPLY_TIMEOUT_100NS (-30000000LL)   /* 3 seconds, relative */

typedef struct _AAV_GLOBALS {
    PFLT_FILTER Filter;
    PFLT_PORT ServerPort;
    PFLT_PORT ClientPort;
    HANDLE ClientProcessId;
} AAV_GLOBALS;

static AAV_GLOBALS g;

DRIVER_INITIALIZE DriverEntry;
static NTSTATUS AavUnload(_In_ FLT_FILTER_UNLOAD_FLAGS Flags);
static NTSTATUS AavInstanceSetup(_In_ PCFLT_RELATED_OBJECTS FltObjects, _In_ FLT_INSTANCE_SETUP_FLAGS Flags,
                                 _In_ DEVICE_TYPE VolumeDeviceType, _In_ FLT_FILESYSTEM_TYPE VolumeFilesystemType);
static FLT_PREOP_CALLBACK_STATUS AavPreCreate(_Inout_ PFLT_CALLBACK_DATA Data, _In_ PCFLT_RELATED_OBJECTS FltObjects,
                                              _Flt_CompletionContext_Outptr_ PVOID *CompletionContext);
static NTSTATUS AavConnect(_In_ PFLT_PORT ClientPort, _In_opt_ PVOID ServerPortCookie,
                           _In_reads_bytes_opt_(SizeOfContext) PVOID ConnectionContext, _In_ ULONG SizeOfContext,
                           _Outptr_result_maybenull_ PVOID *ConnectionPortCookie);
static VOID AavDisconnect(_In_opt_ PVOID ConnectionCookie);

static const FLT_OPERATION_REGISTRATION Callbacks[] = {
    { IRP_MJ_CREATE, 0, AavPreCreate, NULL },
    { IRP_MJ_OPERATION_END }
};

static const FLT_REGISTRATION Registration = {
    sizeof(FLT_REGISTRATION), FLT_REGISTRATION_VERSION, 0,
    NULL, Callbacks, AavUnload, AavInstanceSetup,
    NULL, NULL, NULL, NULL, NULL, NULL
};

NTSTATUS DriverEntry(_In_ PDRIVER_OBJECT DriverObject, _In_ PUNICODE_STRING RegistryPath)
{
    NTSTATUS status;
    PSECURITY_DESCRIPTOR sd = NULL;
    OBJECT_ATTRIBUTES oa;
    UNICODE_STRING portName;
    UNREFERENCED_PARAMETER(RegistryPath);

    RtlZeroMemory(&g, sizeof(g));
    status = FltRegisterFilter(DriverObject, &Registration, &g.Filter);
    if (!NT_SUCCESS(status)) {
        return status;
    }
    status = FltBuildDefaultSecurityDescriptor(&sd, FLT_PORT_ALL_ACCESS);   /* SYSTEM + Administrators only */
    if (NT_SUCCESS(status)) {
        RtlInitUnicodeString(&portName, AAV_PORT_NAME);
        InitializeObjectAttributes(&oa, &portName, OBJ_KERNEL_HANDLE | OBJ_CASE_INSENSITIVE, NULL, sd);
        status = FltCreateCommunicationPort(g.Filter, &g.ServerPort, &oa, NULL, AavConnect, AavDisconnect, NULL, 1);
        FltFreeSecurityDescriptor(sd);
    }
    if (NT_SUCCESS(status)) {
        status = FltStartFiltering(g.Filter);
    }
    if (!NT_SUCCESS(status)) {
        if (g.ServerPort) {
            FltCloseCommunicationPort(g.ServerPort);
        }
        FltUnregisterFilter(g.Filter);
    }
    return status;
}

static NTSTATUS AavUnload(_In_ FLT_FILTER_UNLOAD_FLAGS Flags)
{
    UNREFERENCED_PARAMETER(Flags);
    FltCloseCommunicationPort(g.ServerPort);
    FltUnregisterFilter(g.Filter);
    return STATUS_SUCCESS;
}

static NTSTATUS AavInstanceSetup(_In_ PCFLT_RELATED_OBJECTS FltObjects, _In_ FLT_INSTANCE_SETUP_FLAGS Flags,
                                 _In_ DEVICE_TYPE VolumeDeviceType, _In_ FLT_FILESYSTEM_TYPE VolumeFilesystemType)
{
    UNREFERENCED_PARAMETER(FltObjects);
    UNREFERENCED_PARAMETER(Flags);
    /* Local disks only (NTFS, ReFS, FAT/exFAT for removable media); skip network redirectors. */
    if (VolumeDeviceType != FILE_DEVICE_DISK_FILE_SYSTEM) {
        return STATUS_FLT_DO_NOT_ATTACH;
    }
    switch (VolumeFilesystemType) {
    case FLT_FSTYPE_NTFS: case FLT_FSTYPE_REFS: case FLT_FSTYPE_FAT: case FLT_FSTYPE_EXFAT:
        return STATUS_SUCCESS;
    default:
        return STATUS_FLT_DO_NOT_ATTACH;
    }
}

static NTSTATUS AavConnect(_In_ PFLT_PORT ClientPort, _In_opt_ PVOID ServerPortCookie,
                           _In_reads_bytes_opt_(SizeOfContext) PVOID ConnectionContext, _In_ ULONG SizeOfContext,
                           _Outptr_result_maybenull_ PVOID *ConnectionPortCookie)
{
    UNREFERENCED_PARAMETER(ServerPortCookie);
    UNREFERENCED_PARAMETER(ConnectionContext);
    UNREFERENCED_PARAMETER(SizeOfContext);
    g.ClientProcessId = PsGetCurrentProcessId();
    g.ClientPort = ClientPort;
    *ConnectionPortCookie = NULL;
    return STATUS_SUCCESS;
}

static VOID AavDisconnect(_In_opt_ PVOID ConnectionCookie)
{
    UNREFERENCED_PARAMETER(ConnectionCookie);
    FltCloseClientPort(g.Filter, &g.ClientPort);
    g.ClientProcessId = NULL;
}

static FLT_PREOP_CALLBACK_STATUS AavPreCreate(_Inout_ PFLT_CALLBACK_DATA Data, _In_ PCFLT_RELATED_OBJECTS FltObjects,
                                              _Flt_CompletionContext_Outptr_ PVOID *CompletionContext)
{
    PFLT_FILE_NAME_INFORMATION name = NULL;
    PAAV_REQUEST request = NULL;
    AAV_REPLY reply;
    ULONG replyLength = sizeof(reply);
    LARGE_INTEGER timeout;
    ACCESS_MASK access;
    ULONG options, disposition;
    NTSTATUS status;
    FLT_PREOP_CALLBACK_STATUS result = FLT_PREOP_SUCCESS_NO_CALLBACK;

    UNREFERENCED_PARAMETER(FltObjects);
    *CompletionContext = NULL;

    if (g.ClientPort == NULL || Data->RequestorMode == KernelMode ||
        PsGetCurrentProcessId() == g.ClientProcessId || KeGetCurrentIrql() != PASSIVE_LEVEL) {
        return FLT_PREOP_SUCCESS_NO_CALLBACK;
    }
    options = Data->Iopb->Parameters.Create.Options;
    disposition = (options >> 24) & 0xFF;
    access = Data->Iopb->Parameters.Create.SecurityContext->DesiredAccess;
    if (FlagOn(options, FILE_DIRECTORY_FILE) || FlagOn(Data->Iopb->OperationFlags, SL_OPEN_PAGING_FILE) ||
        FlagOn(Data->Iopb->OperationFlags, SL_OPEN_TARGET_DIRECTORY) ||
        !(access & (FILE_READ_DATA | FILE_EXECUTE | GENERIC_READ | GENERIC_EXECUTE | GENERIC_ALL)) ||
        disposition == FILE_CREATE || disposition == FILE_SUPERSEDE || disposition == FILE_OVERWRITE ||
        disposition == FILE_OVERWRITE_IF) {
        return FLT_PREOP_SUCCESS_NO_CALLBACK;           /* nothing existing to scan, or no data access */
    }

    status = FltGetFileNameInformation(Data, FLT_FILE_NAME_NORMALIZED | FLT_FILE_NAME_QUERY_DEFAULT, &name);
    if (!NT_SUCCESS(status)) {
        return FLT_PREOP_SUCCESS_NO_CALLBACK;
    }
    request = (PAAV_REQUEST)ExAllocatePool2(POOL_FLAG_PAGED, sizeof(AAV_REQUEST), AAV_POOL_TAG);
    if (request == NULL) {
        FltReleaseFileNameInformation(name);
        return FLT_PREOP_SUCCESS_NO_CALLBACK;
    }
    request->ProcessId = HandleToULong(PsGetCurrentProcessId());
    request->Operation = (access & (FILE_EXECUTE | GENERIC_EXECUTE)) ? AAV_OP_EXEC : AAV_OP_OPEN;
    RtlStringCchCopyNW(request->Path, AAV_MAX_PATH_CHARS, name->Name.Buffer, name->Name.Length / sizeof(WCHAR));
    FltReleaseFileNameInformation(name);

    timeout.QuadPart = AAV_REPLY_TIMEOUT_100NS;
    RtlZeroMemory(&reply, sizeof(reply));
    reply.Allow = 1;
    status = FltSendMessage(g.Filter, &g.ClientPort, request, sizeof(AAV_REQUEST), &reply, &replyLength, &timeout);
    if (status == STATUS_SUCCESS && replyLength >= sizeof(AAV_REPLY) && reply.Allow == 0) {
        Data->IoStatus.Status = STATUS_ACCESS_DENIED;
        Data->IoStatus.Information = 0;
        result = FLT_PREOP_COMPLETE;
    }
    ExFreePoolWithTag(request, AAV_POOL_TAG);
    return result;
}
