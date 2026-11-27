# File-handler capability matrix

From `control-plane/app/routers/files.py` (`HANDLERS`). Every type is stored as an opaque, malware-scanned, checksummed blob; preview, edit and conversion exist only where listed. Tests: `control-plane/tests/test_files.py`.

| MIME type | Store | Preview | Edit | Convert to | Status | Note |
|---|---|---|---|---|---|---|
| application/gzip | yes | yes | no | — | tested | preview = entry listing |
| application/json | yes | yes | yes | text/csv | tested |  |
| application/pdf | yes | yes | no | — | tested | inline in the browser's PDF viewer; deny-all CSP |
| application/vnd.openxmlformats-officedocument.presentationml.presentation | yes | yes | no | text/plain | tested | preview = slide text |
| application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | yes | yes | no | text/csv | tested | preview = sheets and cells; convert = first sheet |
| application/vnd.openxmlformats-officedocument.wordprocessingml.document | yes | yes | no | text/plain | tested | preview = extracted text |
| application/x-tar | yes | yes | no | — | tested | preview = entry listing |
| application/xml | yes | yes | yes | — | tested |  |
| application/zip | yes | yes | no | — | tested | preview = entry listing; bulk import/export supported |
| audio/flac | yes | yes | no | — | tested | inline in the browser's media player (range requests) |
| audio/mpeg | yes | yes | no | — | tested | inline in the browser's media player (range requests) |
| audio/ogg | yes | yes | no | — | tested | inline in the browser's media player (range requests) |
| audio/wav | yes | yes | no | — | tested | inline in the browser's media player (range requests) |
| image/gif | yes | yes | no | — | tested |  |
| image/jpeg | yes | yes | no | — | tested |  |
| image/png | yes | yes | no | — | tested |  |
| image/webp | yes | yes | no | — | tested |  |
| text/csv | yes | yes | yes | application/json | tested |  |
| text/markdown | yes | yes | yes | — | tested |  |
| text/plain | yes | yes | yes | — | tested |  |
| video/mp4 | yes | yes | no | — | tested | inline in the browser's media player (range requests) |
| video/webm | yes | yes | no | — | tested | inline in the browser's media player (range requests) |
| any other type | yes | no | no | — | tested | opaque blob |
