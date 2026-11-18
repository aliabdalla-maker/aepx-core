# Locale coverage matrix

Generated from `shared/i18n/*.json` by `tools/gen_matrices.py`. 1 of 100 catalogue locales are complete; the rest fall back to English and are reported as unavailable in the console. No machine translation has been added: each locale needs a translator and per-locale QA (L10N-11) before it is marked complete.

Locale-aware formatting (dates, numbers, currency, plurals, collation search) uses the browser's Intl APIs for every locale regardless of translation status (tested for en, de, fr, ar in `web/tests/lib.test.ts`).

| Locale | Direction | Keys | Coverage | Status | Fallback chain |
|---|---|---|---|---|---|
| en | ltr | 115/115 | 100.0% | complete | en |
| es | ltr | 0/115 | 0.0% | unavailable | es > en |
| zh-Hans | ltr | 0/115 | 0.0% | unavailable | zh-Hans > zh > en |
| hi | ltr | 0/115 | 0.0% | unavailable | hi > en |
| ar | rtl | 0/115 | 0.0% | unavailable | ar > en |
| fr | ltr | 0/115 | 0.0% | unavailable | fr > en |
| pt | ltr | 0/115 | 0.0% | unavailable | pt > en |
| ru | ltr | 0/115 | 0.0% | unavailable | ru > en |
| bn | ltr | 0/115 | 0.0% | unavailable | bn > en |
| id | ltr | 0/115 | 0.0% | unavailable | id > en |
| ur | rtl | 0/115 | 0.0% | unavailable | ur > en |
| de | ltr | 0/115 | 0.0% | unavailable | de > en |
| ja | ltr | 0/115 | 0.0% | unavailable | ja > en |
| sw | ltr | 0/115 | 0.0% | unavailable | sw > en |
| mr | ltr | 0/115 | 0.0% | unavailable | mr > en |
| te | ltr | 0/115 | 0.0% | unavailable | te > en |
| tr | ltr | 0/115 | 0.0% | unavailable | tr > en |
| ta | ltr | 0/115 | 0.0% | unavailable | ta > en |
| vi | ltr | 0/115 | 0.0% | unavailable | vi > en |
| ko | ltr | 0/115 | 0.0% | unavailable | ko > en |
| it | ltr | 0/115 | 0.0% | unavailable | it > en |
| th | ltr | 0/115 | 0.0% | unavailable | th > en |
| gu | ltr | 0/115 | 0.0% | unavailable | gu > en |
| fa | rtl | 0/115 | 0.0% | unavailable | fa > en |
| pl | ltr | 0/115 | 0.0% | unavailable | pl > en |
| uk | ltr | 0/115 | 0.0% | unavailable | uk > en |
| pa | ltr | 0/115 | 0.0% | unavailable | pa > en |
| ml | ltr | 0/115 | 0.0% | unavailable | ml > en |
| jv | ltr | 0/115 | 0.0% | unavailable | jv > en |
| nl | ltr | 0/115 | 0.0% | unavailable | nl > en |
| ro | ltr | 0/115 | 0.0% | unavailable | ro > en |
| hu | ltr | 0/115 | 0.0% | unavailable | hu > en |
| el | ltr | 0/115 | 0.0% | unavailable | el > en |
| cs | ltr | 0/115 | 0.0% | unavailable | cs > en |
| sv | ltr | 0/115 | 0.0% | unavailable | sv > en |
| fi | ltr | 0/115 | 0.0% | unavailable | fi > en |
| he | rtl | 0/115 | 0.0% | unavailable | he > en |
| da | ltr | 0/115 | 0.0% | unavailable | da > en |
| no | ltr | 0/115 | 0.0% | unavailable | no > en |
| sk | ltr | 0/115 | 0.0% | unavailable | sk > en |
| bg | ltr | 0/115 | 0.0% | unavailable | bg > en |
| sr | ltr | 0/115 | 0.0% | unavailable | sr > en |
| hr | ltr | 0/115 | 0.0% | unavailable | hr > en |
| lt | ltr | 0/115 | 0.0% | unavailable | lt > en |
| lv | ltr | 0/115 | 0.0% | unavailable | lv > en |
| et | ltr | 0/115 | 0.0% | unavailable | et > en |
| sl | ltr | 0/115 | 0.0% | unavailable | sl > en |
| ca | ltr | 0/115 | 0.0% | unavailable | ca > en |
| eu | ltr | 0/115 | 0.0% | unavailable | eu > en |
| gl | ltr | 0/115 | 0.0% | unavailable | gl > en |
| af | ltr | 0/115 | 0.0% | unavailable | af > en |
| am | ltr | 0/115 | 0.0% | unavailable | am > en |
| az | ltr | 0/115 | 0.0% | unavailable | az > en |
| be | ltr | 0/115 | 0.0% | unavailable | be > en |
| bs | ltr | 0/115 | 0.0% | unavailable | bs > en |
| cy | ltr | 0/115 | 0.0% | unavailable | cy > en |
| eo | ltr | 0/115 | 0.0% | unavailable | eo > en |
| fil | ltr | 0/115 | 0.0% | unavailable | fil > en |
| ha | ltr | 0/115 | 0.0% | unavailable | ha > en |
| hy | ltr | 0/115 | 0.0% | unavailable | hy > en |
| ig | ltr | 0/115 | 0.0% | unavailable | ig > en |
| is | ltr | 0/115 | 0.0% | unavailable | is > en |
| ka | ltr | 0/115 | 0.0% | unavailable | ka > en |
| kk | ltr | 0/115 | 0.0% | unavailable | kk > en |
| km | ltr | 0/115 | 0.0% | unavailable | km > en |
| kn | ltr | 0/115 | 0.0% | unavailable | kn > en |
| ku | ltr | 0/115 | 0.0% | unavailable | ku > en |
| ky | ltr | 0/115 | 0.0% | unavailable | ky > en |
| lo | ltr | 0/115 | 0.0% | unavailable | lo > en |
| mk | ltr | 0/115 | 0.0% | unavailable | mk > en |
| mn | ltr | 0/115 | 0.0% | unavailable | mn > en |
| my | ltr | 0/115 | 0.0% | unavailable | my > en |
| ne | ltr | 0/115 | 0.0% | unavailable | ne > en |
| or | ltr | 0/115 | 0.0% | unavailable | or > en |
| ps | rtl | 0/115 | 0.0% | unavailable | ps > en |
| si | ltr | 0/115 | 0.0% | unavailable | si > en |
| sq | ltr | 0/115 | 0.0% | unavailable | sq > en |
| su | ltr | 0/115 | 0.0% | unavailable | su > en |
| tg | ltr | 0/115 | 0.0% | unavailable | tg > en |
| tk | ltr | 0/115 | 0.0% | unavailable | tk > en |
| tl | ltr | 0/115 | 0.0% | unavailable | tl > en |
| uz | ltr | 0/115 | 0.0% | unavailable | uz > en |
| yo | ltr | 0/115 | 0.0% | unavailable | yo > en |
| zu | ltr | 0/115 | 0.0% | unavailable | zu > en |
| xh | ltr | 0/115 | 0.0% | unavailable | xh > en |
| so | ltr | 0/115 | 0.0% | unavailable | so > en |
| rw | ltr | 0/115 | 0.0% | unavailable | rw > en |
| mg | ltr | 0/115 | 0.0% | unavailable | mg > en |
| ny | ltr | 0/115 | 0.0% | unavailable | ny > en |
| sn | ltr | 0/115 | 0.0% | unavailable | sn > en |
| st | ltr | 0/115 | 0.0% | unavailable | st > en |
| tn | ltr | 0/115 | 0.0% | unavailable | tn > en |
| ts | ltr | 0/115 | 0.0% | unavailable | ts > en |
| wo | ltr | 0/115 | 0.0% | unavailable | wo > en |
| yi | rtl | 0/115 | 0.0% | unavailable | yi > en |
| ceb | ltr | 0/115 | 0.0% | unavailable | ceb > en |
| hmn | ltr | 0/115 | 0.0% | unavailable | hmn > en |
| bho | ltr | 0/115 | 0.0% | unavailable | bho > en |
| mai | ltr | 0/115 | 0.0% | unavailable | mai > en |
| sat | ltr | 0/115 | 0.0% | unavailable | sat > en |
