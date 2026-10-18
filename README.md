# 茶候 TeaGuard

AI4Climate 2026项目原型：面向杭州梅家坞周边茶园，将区域天气线索转成可追溯的巡查判断。

## 快速运行

要求Python3.10+与NumPy。已下载的公开数据包含在仓库中，启动不再请求网络。

```text
python server.py --port 50112
```

打开 http://127.0.0.1:50112/ 。可选择2025年的日期回放、切换有标记的输入模拟、调整阈值、记录模拟现场墒情，并生成巡查单。

## 原型讲解与项目说明

- [8页项目介绍PDF](docs/media/TeaGuard_Project.pdf)
- [156.62秒中文配音字幕讲解](docs/media/TeaGuard_Demo.mp4)
- [完整项目说明](docs/PROJECT_DESCRIPTION.md)

演示视频采用实际原型截图与已测结果。个人联系人、报名私有草稿、平台登录资料和账号凭据不属于本仓库内容。

## 数据与结果

使用Open-Meteo提供的ERA5区域再分析，2015-2025共4018天。该网格约25公里，不是茶园传感器或业务天气预报。

训练2015-2021，选择方法2022-2023，误差校准2024，保留测试2025；隔离跨年7天标签窗口。358个测试起点上，3日最高气温MAE：季节均值3.834°C，近期天气延续3.700°C，岭回归2.848°C。点预测35°C事件召回53.85%，误报5、漏报30，不能只由MAE改善推断预警全面更优。

工作台用校准区间上界触发人工复核，本次测试命中64/65个高温窗口，同时有73个误报。误差区间不提供未来覆盖保证，重叠天气窗口不是独立地块试验。

七日参考收支预测保留失败结果，仅作探索性检验，不驱动行动。巡查使用过去7日可复算的ET0减降雨，并要求结合土壤确认。没有测量产量、品质、收入或真实农户采纳率。

## 复现检验

```text
python -m teaguard.model
python -m unittest discover -s tests -v
python scripts/independent_verify.py
```

本地26项测试及1087个独立复算断言通过。浏览器历史回放、模拟变化、巡查单预览和真实下载已进行实际操作验收。

## 资料引用

Weather data by Open-Meteo.com; ERA5 by Copernicus/ECMWF; CC BY4.0。免费天气接口用于本次非商业研究演示。

- https://open-meteo.com/en/docs/historical-weather-api
- https://open-meteo.com/en/licence
- https://www.fao.org/4/x0490e/x0490e00.htm
- https://doi.org/10.3390/agronomy11040619
- https://ai4climate.world/
