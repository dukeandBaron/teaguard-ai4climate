# 原数值AI基线参考

`model.py`是V1冻结模型的原文件副本，未改写、未运行。其SHA-256与BUILD_BINDING.json对原V1模型的记录一致。它使用NumPy实现历史天气特征、岭回归、时间划分和评价；当前应用不导入它，不触发拟合。

完整原项目与重现入口可在原公开提交查看：
https://github.com/dukeandBaron/teaguard-ai4climate/tree/3ba876060cd219facb6d282c840ad5a7ad1f319d

本次原型读取`artifacts/test_predictions.json`和`evaluation.json`，二者与冻结输入绑定。已见2025结果不能为后续新设计充当未见测试。此参考副本不表示本轮新增训练或已经接入实时推理。
