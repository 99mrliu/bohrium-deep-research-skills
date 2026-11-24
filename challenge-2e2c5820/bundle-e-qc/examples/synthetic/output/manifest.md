# 可复算清单（manifest）

- 生成时间：2026-11-24T22:29:25
- 文件总数：10

| 文件 | 字节数 | SHA-256 |
| --- | --- | --- |
| `/Users/liuhengshen/Desktop/bhr_product/2e2c-five/bundle-e-qc/outputs/examples/synthetic/case.json` | 3640 | `354792c935fde610cec5ee229d75537e9c43b4d1cac774aa860aad7c9beb7c4f` |
| `/Users/liuhengshen/Desktop/bhr_product/2e2c-five/bundle-e-qc/outputs/examples/synthetic/task.md` | 1255 | `a06c05d8342ce848ce39268c60de67d412199406ec51c9951a05a174485cbf1d` |
| `/Users/liuhengshen/Desktop/bhr_product/2e2c-five/bundle-e-qc/outputs/examples/synthetic/review_report.md` | 4312 | `e02683197acd4f45a55ae6d69290432736595d67f9dbf8c6eac661691caed638` |
| `/Users/liuhengshen/Desktop/bhr_product/2e2c-five/bundle-e-qc/outputs/examples/synthetic/output/commands.txt` | 660 | `42c5414e06d6865a7f6e304e496ecf0a8a60b2ecb317416e91e9ea71534fa9ef` |
| `/Users/liuhengshen/Desktop/bhr_product/2e2c-five/bundle-e-qc/outputs/examples/synthetic/output/contract_checklist.json` | 1876 | `7b36c7aa58605194ea9be17d0939536f22c3bee1abbefc8e7ec310f08037f468` |
| `/Users/liuhengshen/Desktop/bhr_product/2e2c-five/bundle-e-qc/outputs/examples/synthetic/output/qc_report.md` | 891 | `9decd05e52d40b785a811005eff62f4afd780f30cb0025947edffca96887b087` |
| `/Users/liuhengshen/Desktop/bhr_product/2e2c-five/bundle-e-qc/outputs/examples/synthetic/output/result.json` | 1933 | `d103f7d1d9b01293f9c98001bfead3132702bb8743ff2cae444c0d1a09a72cce` |
| `/Users/liuhengshen/Desktop/bhr_product/2e2c-five/bundle-e-qc/outputs/examples/synthetic/output/result.skeleton.json` | 658 | `9f6c0f656ce9f13163b211feb958cf74f049e800f4ea5f617ac5c6cd0dc71efe` |
| `/Users/liuhengshen/Desktop/bhr_product/2e2c-five/bundle-e-qc/outputs/examples/synthetic/output/review_report.html` | 8317 | `a334ec8f2b2b686b1fe65aa23eaca1375d81af661cafa3f43cef56761862e2a3` |
| `/Users/liuhengshen/Desktop/bhr_product/2e2c-five/bundle-e-qc/outputs/examples/synthetic/output/review_report.md` | 4312 | `e02683197acd4f45a55ae6d69290432736595d67f9dbf8c6eac661691caed638` |

## 复算命令

以下为本流程实际执行的命令行（按序重跑后可用上表哈希核验字节一致性）：

1. `python3 ../../scripts/parse_contract.py case.json output`
2. `cp output/result.skeleton.json output/result.json`
3. `python3 - output/result.json    # heredoc：merge 审查结论（见 run_example.sh）`
4. `cp review_report.md output/review_report.md`
5. `python3 ../../scripts/lint_review.py output/review_report.md --strict`
6. `python3 ../../scripts/validate_result.py case.json output/result.json`
7. `python3 ../../scripts/render_report.py output/review_report.md output/result.json output/review_report.html`
8. `python3 ../../scripts/make_manifest.py case.json task.md review_report.md output -o output --commands output/commands.txt`
9. `python3 ../../scripts/selfcheck.py output case.json`
