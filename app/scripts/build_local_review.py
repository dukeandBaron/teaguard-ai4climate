"""Create and render a source-bound local review PDF with installed PyMuPDF."""

import hashlib
import json
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/pdf"
RENDER = ROOT / "artifacts/pdf_review"
INK = (0.08, 0.23, 0.21)
GREEN = (0.10, 0.46, 0.36)


def text(page, box, content, size=11, color=INK):
    remaining = page.insert_textbox(
        pymupdf.Rect(box),
        content,
        fontname="china-s",
        fontsize=size,
        lineheight=1.55,
        color=color,
    )
    if remaining < 0:
        raise ValueError(f"Review text overflow: {content[:60]}")


def main():
    acceptance = json.loads(
        (ROOT / "artifacts/ENGINEERING_ACCEPTANCE.json").read_text(encoding="utf-8")
    )
    if acceptance["status"] != "PASS_LOCAL_V3_ENGINEERING_ACCEPTANCE":
        raise ValueError("Cannot publish a passing review without acceptance")
    count = next(
        r["tests_run"] for r in acceptance["stage_checks"] if r["stage"] == "unittest"
    )
    OUT.mkdir(parents=True, exist_ok=True)
    RENDER.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    pages = [
        (
            "茶候 · 自然情境工作台",
            "本机 V0.3.1 / 工程审查版 / 2026-10-19",
            "desktop_final.png",
            "同一份天气，核查不同的现场。\n本版连接区域天气、AI地块条件、五张机制证据卡和核查清单。关系图支持拖动与点击；任务勾选、撤销和下载保留前序版本；记录使用本机事务存储。",
            "运行：http://127.0.0.1:50115/\n双击 start_teaguard_nature.cmd，或用已安装的 Python 启动。运行读取本地资料和V1保存预测，无云端模型调用、无新增训练。",
        ),
        (
            "先核对条件，再引用结论",
            "五张卡进入运行判断 / 资料、情境与未知分别保留",
            "evidence_scope_final.png",
            "物种、品种、环境、处理和测量终点逐项核对。\n茶树受控基因表达不换算成田间联合损伤；油菜根际处理不迁移成茶园剂量或增产建议。当前关系图是类型化信息图，边不表示测得的因果强度。",
            "数据：2015-2025年，每格4018天、6个日变量；9个ERA5网格，共36162条网格-日期记录。\n中心数据与V1逐日相同；相邻网格原始最高温相关系数约0.997-0.999。真实地块土壤、损伤、产量标签仍为0。",
        ),
        (
            "把改进做成可复核的行为",
            "固定天气 / 切换条件 / 保留历史 / 本机浏览器交互",
            "data_replay_final.png",
            f"实际验证：{count}项自动测试通过；10个逻辑情境、13组输入变体、3档组件设置、40项行为核查通过。\n逐阶段核对当前源码与固定数据摘要；旧V1的25个冻结文件摘要保持一致。桌面与390像素宽手机视口已操作验收。",
            "研究位置：Transformer可用于过去T天×9网格×6变量的时间编码，或带适用性掩码的证据-情境交互。当前未训练或加载Transformer/GNN；自己的工程增量是适用性约束、固定天气的情境对照、缺失信息的规则分支比较。\n尚无新的真实预报精度、田间效益或独立学术首创证据。本版未替换官网附件或视频，未正式提交。",
        ),
    ]
    for index, (title, subtitle, image, body, details) in enumerate(pages, 1):
        page = doc.new_page(width=595, height=842)
        page.draw_rect(
            pymupdf.Rect(0, 0, 595, 842), color=None, fill=(0.97, 0.98, 0.97)
        )
        text(page, (35, 32, 560, 75), title, 22, GREEN)
        text(page, (35, 82, 560, 115), subtitle, 10)
        page.insert_image(
            pymupdf.Rect(35, 125, 560, 490),
            filename=str(ROOT / "artifacts/screenshots" / image),
            keep_proportion=True,
        )
        text(page, (35, 506, 560, 630), body, 11)
        text(page, (35, 648, 560, 785), details, 10)
        text(
            page,
            (35, 807, 560, 834),
            f"TeaGuard local review  |  {index}/3  |  AI情境不代表田间效果",
            9,
        )
    target = OUT / "TeaGuard_Nature_V3_1_Local_Review.pdf"
    doc.save(target)
    renders = []
    for i, page in enumerate(doc):
        path = RENDER / f"page_{i + 1}.png"
        page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).save(path)
        renders.append(path.relative_to(ROOT).as_posix())
    receipt = {
        "pdf": target.relative_to(ROOT).as_posix(),
        "pages": len(doc),
        "renders": renders,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "acceptance_sha256": hashlib.sha256(
            (ROOT / "artifacts/ENGINEERING_ACCEPTANCE.json").read_bytes()
        ).hexdigest(),
        "visual_review": "PENDING",
    }
    (RENDER / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
