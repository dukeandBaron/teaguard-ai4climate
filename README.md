# 茶候 TeaGuard · V0.3.1

A local working prototype for traceable tea-garden climate inspection.
Historical weather-model outputs and explicitly AI-authored field scenarios are kept separate.

面向梅家坞周边茶园巡查，连接天气线索、情境、文献适用性、任务与模拟反馈。当前没有真实用户试用或农业收益证明。

- [真实网页演示 MP4 / 2分54秒](docs/TeaGuard_Demo_V3_1.mp4)
- [四页项目说明 PDF](docs/TeaGuard_Project_Statement_V3_1.pdf)
- [数据与AI声明](app/submission/DATA_AI_STATEMENT.md)
- [90天验证计划](app/submission/VALIDATION_90_DAYS.md)
- [软件结构与工程审查](app/docs/ARCHITECTURE.md)

## 本机运行

    cd app
    python -B scripts/launch_local.py

浏览器访问 http://127.0.0.1:50115/ 。运行只需Python 3.12标准库，无模型API、GPU训练或依赖下载。127.0.0.1是本机地址，不是公网Demo。

## 验证

使用已有Python/jsonschema和Node，可在app目录执行：

    python -B scripts/verify_portable.py

公开副本包含当前运行应用的48项Python测试、3项前端请求测试，以及十情境/十三变体/四十行为检查。完整本机工作区105项Python测试还包含历史候选校验；其回执作为历史工程证据保留。历史第三方读取缓存不分发，因此相应历史测试不列入公开运行套件。实际运行核心文件与本轮验收源文件一致，分发范围见PUBLIC_REVIEW.json。

## 数据、模型与边界

ERA5公开再分析：9个返回网格、2015—2025年、36162条网格—日期记录；相邻网格高度相关。真实地块损伤、产量和收益标签为0。Weather data by Open-Meteo.com; ERA5 by Copernicus/ECMWF；保存天气数据按CC BY 4.0署名，商用API访问须核对提供方条款。

数值AI使用原V1岭回归的保存预测，本次不重新拟合。V1的2025历史三日高温指标MAE约2.848°C，延续天气约3.700°C；它不代表真实业务预报效果。新增加的是情境与证据决策层、任务依据绑定和本机版本管理。未部署Transformer、GNN或在线大模型。

原V1保留在旧目录与历史提交：
https://github.com/dukeandBaron/teaguard-ai4climate/tree/3ba876060cd219facb6d282c840ad5a7ad1f319d

本仓库公开供评审查看；不新增代码复用许可声明。第三方数据和来源分别按其许可与署名处理。正式赛事提报状态另以官网成功状态和报名编号为准。
