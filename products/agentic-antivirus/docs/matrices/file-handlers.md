# File-handler capability matrix

From `control-plane/app/routers/files.py` (`HANDLERS`). Every type is stored as an opaque, malware-scanned, checksummed blob; preview, edit and conversion exist only where listed. Tests: `control-plane/tests/test_files.py`.

| MIME type | Store | Preview | Edit | Convert to | Status | Note |
|---|---|---|---|---|---|---|
| application/gzip | yes | no | no | — | tested |  |
| application/json | yes | yes | yes | text/csv | tested |  |
| application/pdf | yes | no | no | — | tested | download only; no in-app renderer verified |
| application/vnd.openxmlformats-officedocument.presentationml.presentation | yes | no | no | — | not implemented | opaque: office handler not implemented |
| application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | yes | no | no | — | not implemented | opaque: office handler not implemented |
| application/vnd.openxmlformats-officedocument.wordprocessingml.document | yes | no | no | — | not implemented | opaque: office handler not implemented |
| application/x-tar | yes | no | no | — | tested |  |
| application/xml | yes | yes | yes | — | tested |  |
| application/zip | yes | no | no | — | tested | bulk import/export supported; preview not implemented |
| audio/flac | yes | no | no | — | not implemented | opaque: media handler not implemented |
| audio/mpeg | yes | no | no | — | not implemented | opaque: media handler not implemented |
| audio/ogg | yes | no | no | — | not implemented | opaque: media handler not implemented |
| image/gif | yes | yes | no | — | tested |  |
| image/jpeg | yes | yes | no | — | tested |  |
| image/png | yes | yes | no | — | tested |  |
| text/csv | yes | yes | yes | application/json | tested |  |
| text/markdown | yes | yes | yes | — | tested |  |
| text/plain | yes | yes | yes | — | tested |  |
| video/mp4 | yes | no | no | — | not implemented | opaque: media handler not implemented |
| video/webm | yes | no | no | — | not implemented | opaque: media handler not implemented |
| any other type | yes | no | no | — | tested | opaque blob |
