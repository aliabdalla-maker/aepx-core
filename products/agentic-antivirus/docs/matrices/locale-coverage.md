# Locale coverage matrix

Generated from `shared/i18n/*.json` by `tools/gen_matrices.py`. 75 of 100 catalogue locales are complete; the rest fall back to English and are reported as unavailable in the console. No machine translation has been added: each locale needs a translator and per-locale QA (L10N-11) before it is marked complete.

Locale-aware formatting (dates, numbers, currency, plurals, collation search) uses the browser's Intl APIs for every locale regardless of translation status (tested for en, de, fr, ar in `web/tests/lib.test.ts`).

| Locale | Direction | Keys | Coverage | Status | Fallback chain |
|---|---|---|---|---|---|
| en | ltr | 672/672 | 100.0% | complete | en |
| es | ltr | 672/672 | 100.0% | complete | es > en |
| zh-Hans | ltr | 672/672 | 100.0% | complete | zh-Hans > zh > en |
| hi | ltr | 672/672 | 100.0% | complete | hi > en |
| ar | rtl | 672/672 | 100.0% | complete | ar > en |
| fr | ltr | 672/672 | 100.0% | complete | fr > en |
| pt | ltr | 672/672 | 100.0% | complete | pt > en |
| ru | ltr | 672/672 | 100.0% | complete | ru > en |
| bn | ltr | 0/672 | 0.0% | unavailable | bn > en |
| id | ltr | 672/672 | 100.0% | complete | id > en |
| ur | rtl | 672/672 | 100.0% | complete | ur > en |
| de | ltr | 672/672 | 100.0% | complete | de > en |
| ja | ltr | 672/672 | 100.0% | complete | ja > en |
| sw | ltr | 672/672 | 100.0% | complete | sw > en |
| mr | ltr | 672/672 | 100.0% | complete | mr > en |
| te | ltr | 672/672 | 100.0% | complete | te > en |
| tr | ltr | 0/672 | 0.0% | unavailable | tr > en |
| ta | ltr | 672/672 | 100.0% | complete | ta > en |
| vi | ltr | 672/672 | 100.0% | complete | vi > en |
| ko | ltr | 672/672 | 100.0% | complete | ko > en |
| it | ltr | 672/672 | 100.0% | complete | it > en |
| th | ltr | 672/672 | 100.0% | complete | th > en |
| gu | ltr | 0/672 | 0.0% | unavailable | gu > en |
| fa | rtl | 672/672 | 100.0% | complete | fa > en |
| pl | ltr | 672/672 | 100.0% | complete | pl > en |
| uk | ltr | 672/672 | 100.0% | complete | uk > en |
| pa | ltr | 0/672 | 0.0% | unavailable | pa > en |
| ml | ltr | 672/672 | 100.0% | complete | ml > en |
| jv | ltr | 0/672 | 0.0% | unavailable | jv > en |
| nl | ltr | 672/672 | 100.0% | complete | nl > en |
| ro | ltr | 672/672 | 100.0% | complete | ro > en |
| hu | ltr | 672/672 | 100.0% | complete | hu > en |
| el | ltr | 0/672 | 0.0% | unavailable | el > en |
| cs | ltr | 672/672 | 100.0% | complete | cs > en |
| sv | ltr | 672/672 | 100.0% | complete | sv > en |
| fi | ltr | 672/672 | 100.0% | complete | fi > en |
| he | rtl | 672/672 | 100.0% | complete | he > en |
| da | ltr | 672/672 | 100.0% | complete | da > en |
| no | ltr | 672/672 | 100.0% | complete | no > en |
| sk | ltr | 672/672 | 100.0% | complete | sk > en |
| bg | ltr | 672/672 | 100.0% | complete | bg > en |
| sr | ltr | 672/672 | 100.0% | complete | sr > en |
| hr | ltr | 672/672 | 100.0% | complete | hr > en |
| lt | ltr | 672/672 | 100.0% | complete | lt > en |
| lv | ltr | 672/672 | 100.0% | complete | lv > en |
| et | ltr | 672/672 | 100.0% | complete | et > en |
| sl | ltr | 672/672 | 100.0% | complete | sl > en |
| ca | ltr | 672/672 | 100.0% | complete | ca > en |
| eu | ltr | 672/672 | 100.0% | complete | eu > en |
| gl | ltr | 672/672 | 100.0% | complete | gl > en |
| af | ltr | 672/672 | 100.0% | complete | af > en |
| am | ltr | 0/672 | 0.0% | unavailable | am > en |
| az | ltr | 0/672 | 0.0% | unavailable | az > en |
| be | ltr | 672/672 | 100.0% | complete | be > en |
| bs | ltr | 672/672 | 100.0% | complete | bs > en |
| cy | ltr | 672/672 | 100.0% | complete | cy > en |
| eo | ltr | 672/672 | 100.0% | complete | eo > en |
| fil | ltr | 672/672 | 100.0% | complete | fil > en |
| ha | ltr | 672/672 | 100.0% | complete | ha > en |
| hy | ltr | 0/672 | 0.0% | unavailable | hy > en |
| ig | ltr | 672/672 | 100.0% | complete | ig > en |
| is | ltr | 672/672 | 100.0% | complete | is > en |
| ka | ltr | 0/672 | 0.0% | unavailable | ka > en |
| kk | ltr | 672/672 | 100.0% | complete | kk > en |
| km | ltr | 672/672 | 100.0% | complete | km > en |
| kn | ltr | 672/672 | 100.0% | complete | kn > en |
| ku | ltr | 0/672 | 0.0% | unavailable | ku > en |
| ky | ltr | 672/672 | 100.0% | complete | ky > en |
| lo | ltr | 672/672 | 100.0% | complete | lo > en |
| mk | ltr | 672/672 | 100.0% | complete | mk > en |
| mn | ltr | 0/672 | 0.0% | unavailable | mn > en |
| my | ltr | 0/672 | 0.0% | unavailable | my > en |
| ne | ltr | 672/672 | 100.0% | complete | ne > en |
| or | ltr | 0/672 | 0.0% | unavailable | or > en |
| ps | rtl | 672/672 | 100.0% | complete | ps > en |
| si | ltr | 672/672 | 100.0% | complete | si > en |
| sq | ltr | 0/672 | 0.0% | unavailable | sq > en |
| su | ltr | 0/672 | 0.0% | unavailable | su > en |
| tg | ltr | 0/672 | 0.0% | unavailable | tg > en |
| tk | ltr | 0/672 | 0.0% | unavailable | tk > en |
| tl | ltr | 672/672 | 100.0% | complete | tl > en |
| uz | ltr | 0/672 | 0.0% | unavailable | uz > en |
| yo | ltr | 672/672 | 100.0% | complete | yo > en |
| zu | ltr | 672/672 | 100.0% | complete | zu > en |
| xh | ltr | 0/672 | 0.0% | unavailable | xh > en |
| so | ltr | 672/672 | 100.0% | complete | so > en |
| rw | ltr | 0/672 | 0.0% | unavailable | rw > en |
| mg | ltr | 672/672 | 100.0% | complete | mg > en |
| ny | ltr | 0/672 | 0.0% | unavailable | ny > en |
| sn | ltr | 672/672 | 100.0% | complete | sn > en |
| st | ltr | 672/672 | 100.0% | complete | st > en |
| tn | ltr | 672/672 | 100.0% | complete | tn > en |
| ts | ltr | 672/672 | 100.0% | complete | ts > en |
| wo | ltr | 0/672 | 0.0% | unavailable | wo > en |
| yi | rtl | 672/672 | 100.0% | complete | yi > en |
| ceb | ltr | 672/672 | 100.0% | complete | ceb > en |
| hmn | ltr | 0/672 | 0.0% | unavailable | hmn > en |
| bho | ltr | 672/672 | 100.0% | complete | bho > en |
| mai | ltr | 672/672 | 100.0% | complete | mai > en |
| sat | ltr | 0/672 | 0.0% | unavailable | sat > en |
