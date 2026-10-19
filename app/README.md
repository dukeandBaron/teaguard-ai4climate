# TeaGuard V0.3.1 public runtime distribution

本目录为当前应用的公开分发副本。运行：python -B scripts/launch_local.py；本机地址：http://127.0.0.1:50115/ 。

代码、状态模型、规则、证据、冻结天气与浏览器资源均来自已验收的V0.3.1。项目说明和视频位于仓库根目录docs/，数据与AI声明及90天计划位于submission/。

可移植验证：python -B scripts/verify_portable.py。当前应用48项Python与3项前端请求测试，另有10情境/13变体/40行为核查。完整本机工作区105项还包含未随历史第三方读取缓存分发的候选校验；不要将两种验证范围混同。

严格工作区核对工具verify_engineering.py需要开发者历史根目录，仅为本机完整性证据。公开副本使用verify_portable.py，不要求这些绝对路径。

历史读取缓存未重新分发，FAO概念来源为https://www.fao.org/4/x0490e/x0490e04.htm；自己的证据摘要与来源索引保留。原V1模型参考位于reference_baseline/，不由当前运行入口导入或拟合。

runtime/是运行时私有数据库与诊断目录，未公开；实际反馈仍为AI模拟。
