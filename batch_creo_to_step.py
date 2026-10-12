# -*- coding: utf-8 -*-
"""
batch_creo_to_step.py

功能：
1. 启动后选择包含 Creo PRT/ASM 文件的文件夹；
2. 识别 .prt、.asm 以及带版本号的 Creo 文件；
3. 对同名模型只选取最高数字版本；
4. 在所选文件夹下创建 STP 文件夹；
5. 自动生成 Creo Distributed Batch 使用的 DXC 文件；
6. 调用 ptcdbatch.bat 以无图形方式批量转换；
7. 检查输出的 STP/STEP 文件；
8. 保存批处理日志。

重要说明：
- Python 不直接读取 Creo 私有格式；
- 实际转换由 Creo Distributed Batch 完成；
- 本程序负责准备任务并调用 Creo；
- 装配体转换时，必须保证其依赖零件能够被 Creo 找到。

运行方式：

python D:\\Creo2dxf\\batch_creo_to_step.py

也支持直接传入文件夹：

python D:\\Creo2dxf\\batch_creo_to_step.py "D:\\Models"

仅生成 DXC、不运行转换：

python D:\\Creo2dxf\\batch_creo_to_step.py "D:\\Models" --dry-run
"""

import os
import re
import sys
import time
import shutil
import subprocess
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path


# ============================================================
# 用户配置
# ============================================================

# Creo Distributed Batch 启动脚本。
PTC_DBATCH_BAT = (
    r"C:\PTC\Creo 12.4.3.0"
    r"\Parametric\bin\ptcdbatch.bat"
)

# STEP 3D Export 的任务类型定义。
STEP_TTD_FILE = (
    r"C:\PTC\Creo 12.4.3.0"
    r"\Common Files\text\ttds"
    r"\step_3d_export.ttd"
)

# 可选：Creo 配置文件。
#
# 如果留空：
#     不在 DXC 中添加 ConfigFile。
#
# 如果你以后需要指定 config.pro，可改为：
#
# CREO_CONFIG_FILE = r"D:\Creo2dxf\config.pro"
#
CREO_CONFIG_FILE = ""

# 是否递归扫描子文件夹。
#
# False：
#     仅处理选择文件夹第一层中的 PRT/ASM。
#
# True：
#     递归扫描所有子文件夹。
#
RECURSIVE_SCAN = False

# 是否只处理每个模型的最高数字版本。
#
# 例如同时存在：
#     plate.prt.1
#     plate.prt.3
#     plate.prt.8
#
# True 时只处理：
#     plate.prt.8
#
ONLY_LATEST_VERSION = True

# 同名无版本文件和数字版本文件同时存在时：
#
# True：
#     优先采用数字版本号最高的文件。
#
# False：
#     优先采用不带数字版本号的文件。
#
PREFER_NUMBERED_VERSION = True

# 输出子文件夹名称。
OUTPUT_FOLDER_NAME = "STP"

# 工作文件子文件夹。
#
# DXC 和日志放在：
#     选择文件夹\STP\_batch_work
#
WORK_FOLDER_NAME = "_batch_work"

# Distributed Batch 的本地执行标识。
DSQM_VALUE = "_LOCAL"

# DXC 中的 Output 参数。
#
# 当前使用 2，与常见的指定 OutputDir 的 DXC 示例一致。
# 如果你的 Creo 12 实际保存的 DXC 使用其他值，
# 应以 Creo 12 UI 保存出来的 DXC 为准。
DXC_OUTPUT_MODE = "2"

# 是否覆盖已有的同名 STEP。
#
# 注意：
# Distributed Batch 本身如何处理已有文件，
# 可能还受 Creo 配置影响。
#
# 本选项为 True 时，在运行任务前删除 STP 目录下已有的
# 同名 .stp 和 .step 文件。
OVERWRITE_EXISTING_STEP = True

# 转换完成后是否保留 DXC 文件。
KEEP_DXC_FILE = True

# 转换完成后是否保留完整控制台日志。
KEEP_BATCH_LOG = True

# 是否先处理 PRT，再处理 ASM。
#
# 这对输出顺序有帮助。
# 但装配体调用的是源 Creo 模型，不依赖刚生成的 STEP。
PARTS_BEFORE_ASSEMBLIES = True


# ============================================================
# 日志
# ============================================================

def log(message=""):
    """
    输出日志并立即刷新。
    """
    print(message, flush=True)


# ============================================================
# 路径处理
# ============================================================

def normalize_path(path_text):
    """
    规范化 Windows 路径。
    """
    if path_text is None:
        return ""

    path_text = str(path_text).strip()
    path_text = path_text.strip('"')
    path_text = path_text.strip("'")

    if not path_text:
        return ""

    return os.path.abspath(
        os.path.normpath(path_text)
    )


def validate_required_files():
    """
    检查 Creo Distributed Batch 所需文件。
    """
    missing_items = []

    if not os.path.isfile(PTC_DBATCH_BAT):
        missing_items.append(
            "找不到 ptcdbatch.bat：\n"
            f"{PTC_DBATCH_BAT}"
        )

    if not os.path.isfile(STEP_TTD_FILE):
        missing_items.append(
            "找不到 step_3d_export.ttd：\n"
            f"{STEP_TTD_FILE}"
        )

    if (
        CREO_CONFIG_FILE
        and not os.path.isfile(CREO_CONFIG_FILE)
    ):
        missing_items.append(
            "找不到指定的 Creo 配置文件：\n"
            f"{CREO_CONFIG_FILE}"
        )

    if missing_items:
        raise FileNotFoundError(
            "\n\n".join(missing_items)
        )


# ============================================================
# 文件夹选择
# ============================================================

def select_folder_with_tkinter():
    """
    使用普通 Python 的 tkinter 弹出文件夹选择窗口。
    """
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()

    try:
        root.attributes("-topmost", True)
    except Exception:
        pass

    root.update()

    selected_folder = filedialog.askdirectory(
        title="请选择包含 Creo PRT/ASM 文件的文件夹",
        mustexist=True,
    )

    root.destroy()

    return normalize_path(selected_folder)



def get_input_folder():
    """
    获取输入文件夹。

    顺序：
    1. 命令行参数；
    2. tkinter 文件夹选择窗口；
    3. 控制台输入。
    """
    for argument in sys.argv[1:]:
        if argument.lower() == "--dry-run":
            continue

        candidate = normalize_path(argument)

        if os.path.isdir(candidate):
            log(
                "使用命令行指定的文件夹："
                f"{candidate}"
            )
            return candidate

    try:
        log("正在打开文件夹选择窗口...")

        selected_folder = (
            select_folder_with_tkinter()
        )

        if selected_folder:
            if not os.path.isdir(selected_folder):
                raise NotADirectoryError(
                    f"选择的路径不是有效文件夹："
                    f"{selected_folder}"
                )

            return selected_folder

        raise RuntimeError(
            "用户取消了文件夹选择。"
        )

    except Exception as tkinter_error:
        log(
            "文件夹选择窗口未能使用："
            f"{tkinter_error}"
        )

    try:
        folder_text = input(
            "\n请输入包含 PRT/ASM 的完整文件夹路径：\n"
        )
    except Exception as input_error:
        raise RuntimeError(
            "无法获取输入文件夹。"
            f"\n详细错误：{input_error}"
        )

    selected_folder = normalize_path(
        folder_text
    )

    if not selected_folder:
        raise RuntimeError(
            "没有选择或输入文件夹。"
        )

    if not os.path.isdir(selected_folder):
        raise NotADirectoryError(
            f"文件夹不存在：{selected_folder}"
        )

    return selected_folder


# ============================================================
# Creo 文件名解析
# ============================================================

# 支持以下形式：
#
# plate.prt
# plate.prt.1
# plate.prt.26
# assembly.asm
# assembly.asm.7
#
CREO_FILE_PATTERN = re.compile(
    r"^(?P<model_name>.+?)"
    r"\.(?P<model_type>prt|asm)"
    r"(?:\.(?P<version>\d+))?$",
    re.IGNORECASE,
)


def parse_creo_file_name(file_name):
    """
    解析 Creo PRT/ASM 文件名。

    Returns
    -------
    dict or None

    返回示例：

    {
        "model_name": "plate",
        "model_type": "prt",
        "version": 8,
        "has_version": True,
        "logical_name": "plate.prt"
    }
    """
    match = CREO_FILE_PATTERN.match(
        file_name
    )

    if match is None:
        return None

    model_name = match.group("model_name")
    model_type = (
        match.group("model_type").lower()
    )
    version_text = match.group("version")

    if version_text is None:
        version = None
        has_version = False
    else:
        version = int(version_text)
        has_version = True

    logical_name = (
        f"{model_name}.{model_type}"
    )

    return {
        "model_name": model_name,
        "model_type": model_type,
        "version": version,
        "has_version": has_version,
        "logical_name": logical_name,
    }


def build_model_key(file_path, root_folder):
    """
    生成模型分组键。

    非递归扫描时：
        按逻辑模型名分组。

    递归扫描时：
        按相对目录 + 逻辑模型名分组。

    这样不同子目录中的同名模型不会被误认为同一个模型。
    """
    parsed = parse_creo_file_name(
        os.path.basename(file_path)
    )

    if parsed is None:
        return None

    if RECURSIVE_SCAN:
        relative_parent = os.path.relpath(
            os.path.dirname(file_path),
            root_folder,
        ).lower()
    else:
        relative_parent = ""

    return (
        relative_parent,
        parsed["logical_name"].lower(),
    )


def choose_preferred_creo_file(
    current_file,
    candidate_file,
):
    """
    在同一逻辑模型的多个版本中选取需要处理的文件。
    """
    if current_file is None:
        return candidate_file

    current_info = parse_creo_file_name(
        os.path.basename(current_file)
    )

    candidate_info = parse_creo_file_name(
        os.path.basename(candidate_file)
    )

    if current_info is None:
        return candidate_file

    if candidate_info is None:
        return current_file

    current_has_version = (
        current_info["has_version"]
    )
    candidate_has_version = (
        candidate_info["has_version"]
    )

    # 两者均带数字版本号，选择版本号更大的。
    if (
        current_has_version
        and candidate_has_version
    ):
        if (
            candidate_info["version"]
            > current_info["version"]
        ):
            return candidate_file

        return current_file

    # 一个带版本号，一个不带版本号。
    if (
        candidate_has_version
        and not current_has_version
    ):
        if PREFER_NUMBERED_VERSION:
            return candidate_file

        return current_file

    if (
        current_has_version
        and not candidate_has_version
    ):
        if PREFER_NUMBERED_VERSION:
            return current_file

        return candidate_file

    # 两者都不带版本号。
    # 理论上同一目录中不应出现两个完全同名文件。
    # 保持先发现的文件。
    return current_file


# ============================================================
# 扫描 Creo 模型
# ============================================================

def collect_creo_files(root_folder):
    """
    扫描 Creo PRT/ASM 文件。

    Returns
    -------
    list[dict]

    每个元素包含：
    - file_path
    - model_name
    - model_type
    - version
    - logical_name
    """
    all_candidates = []

    if RECURSIVE_SCAN:
        for current_root, directory_names, file_names in os.walk(
            root_folder
        ):
            # 避免重新扫描输出目录。
            directory_names[:] = [
                directory_name
                for directory_name in directory_names
                if directory_name.lower()
                != OUTPUT_FOLDER_NAME.lower()
            ]

            for file_name in file_names:
                parsed = parse_creo_file_name(
                    file_name
                )

                if parsed is None:
                    continue

                all_candidates.append(
                    os.path.join(
                        current_root,
                        file_name,
                    )
                )
    else:
        for file_name in os.listdir(root_folder):
            file_path = os.path.join(
                root_folder,
                file_name,
            )

            if not os.path.isfile(file_path):
                continue

            parsed = parse_creo_file_name(
                file_name
            )

            if parsed is None:
                continue

            all_candidates.append(file_path)

    if not ONLY_LATEST_VERSION:
        selected_paths = all_candidates
    else:
        selected_by_model = {}

        for candidate_file in all_candidates:
            model_key = build_model_key(
                candidate_file,
                root_folder,
            )

            if model_key is None:
                continue

            current_file = selected_by_model.get(
                model_key
            )

            selected_by_model[model_key] = (
                choose_preferred_creo_file(
                    current_file=current_file,
                    candidate_file=candidate_file,
                )
            )

        selected_paths = list(
            selected_by_model.values()
        )

    models = []

    for file_path in selected_paths:
        parsed = parse_creo_file_name(
            os.path.basename(file_path)
        )

        if parsed is None:
            continue

        models.append({
            "file_path": os.path.abspath(
                file_path
            ),
            "model_name": parsed["model_name"],
            "model_type": parsed["model_type"],
            "version": parsed["version"],
            "has_version": parsed["has_version"],
            "logical_name": parsed["logical_name"],
        })

    if PARTS_BEFORE_ASSEMBLIES:
        type_order = {
            "prt": 0,
            "asm": 1,
        }

        models.sort(
            key=lambda item: (
                type_order.get(
                    item["model_type"],
                    99,
                ),
                item["logical_name"].lower(),
                item["file_path"].lower(),
            )
        )
    else:
        models.sort(
            key=lambda item: (
                item["logical_name"].lower(),
                item["file_path"].lower(),
            )
        )

    return models


# ============================================================
# 输出文件预测与清理
# ============================================================

def get_possible_step_paths(
    output_folder,
    model,
):
    """
    返回一个模型可能生成的 STEP 文件路径。

    Creo/TTD 的实际后缀可能是 .stp 或 .step，
    所以同时检查两种。
    """
    model_name = model["model_name"]

    return [
        os.path.join(
            output_folder,
            model_name + ".stp",
        ),
        os.path.join(
            output_folder,
            model_name + ".step",
        ),
    ]


def remove_existing_step_outputs(
    output_folder,
    models,
):
    """
    删除即将生成的同名 STEP 文件。
    """
    removed_files = []

    if not OVERWRITE_EXISTING_STEP:
        return removed_files

    for model in models:
        for possible_path in get_possible_step_paths(
            output_folder,
            model,
        ):
            if not os.path.isfile(possible_path):
                continue

            os.remove(possible_path)
            removed_files.append(possible_path)

    return removed_files


# ============================================================
# 生成 DXC 文件
# ============================================================

def indent_xml(element, level=0):
    """
    为 ElementTree 添加便于查看的缩进。
    """
    indentation = "\n" + "  " * level

    if len(element):
        if (
            element.text is None
            or not element.text.strip()
        ):
            element.text = (
                indentation + "  "
            )

        for child in element:
            indent_xml(
                child,
                level + 1,
            )

        if (
            child.tail is None
            or not child.tail.strip()
        ):
            child.tail = indentation

    if level > 0:
        if (
            element.tail is None
            or not element.tail.strip()
        ):
            element.tail = indentation


def create_dxc_file(
models,
output_folder,
dxc_file_path,
):
    r"""
    生成 Creo Distributed Batch 的 DXC 文件。

    生成结构：

    <DXC>
      <Group
          TTD="...step_3d_export.ttd"
          DSQM="_LOCAL"
          Name="STEP 3D Export"
          Output="2"
          OutputDir="...\\STP"
          VaultResults="0"
          PrimaryContent="0">

        <Object>...\part.prt.8</Object>
        <Object>...\assembly.asm.3</Object>

        <ConfigFile>...\config.pro</ConfigFile>
      </Group>
    </DXC>

    注意：
    DXC 的细节存在版本差异的可能。
    当前结构来自常见的 Distributed Batch DXC 形式。
    如果 Creo 12 拒绝解析，应以 Creo 12 UI 保存出的
    DXC 文件结构为准。
    """
    root = ET.Element("DXC")

    group_attributes = {
        "TTD": os.path.abspath(
            STEP_TTD_FILE
        ),
        "DSQM": DSQM_VALUE,
        "Name": "STEP 3D Export",
        "Output": str(DXC_OUTPUT_MODE),
        "OutputDir": os.path.abspath(
            output_folder
        ),
        "VaultResults": "0",
        "PrimaryContent": "0",
    }

    group = ET.SubElement(
        root,
        "Group",
        group_attributes,
    )

    for model in models:
        object_element = ET.SubElement(
            group,
            "Object",
        )

        object_element.text = os.path.abspath(
            model["file_path"]
        )

    if CREO_CONFIG_FILE:
        config_element = ET.SubElement(
            group,
            "ConfigFile",
        )

        config_element.text = os.path.abspath(
            CREO_CONFIG_FILE
        )

    indent_xml(root)

    tree = ET.ElementTree(root)

    os.makedirs(
        os.path.dirname(dxc_file_path),
        exist_ok=True,
    )

    tree.write(
        dxc_file_path,
        encoding="utf-8",
        xml_declaration=True,
    )

    if not os.path.isfile(dxc_file_path):
        raise RuntimeError(
            "DXC 文件写入后不存在："
            f"{dxc_file_path}"
        )

    if os.path.getsize(dxc_file_path) <= 0:
        raise RuntimeError(
            "DXC 文件大小为 0："
            f"{dxc_file_path}"
        )


# ============================================================
# 执行 Distributed Batch
# ============================================================

def build_process_environment():
    """
    创建子进程环境变量。

    当前不主动修改 PTC 环境，
    由 ptcdbatch.bat 设置其所需运行环境。
    """
    environment = os.environ.copy()

    # 确保 Python 子进程日志能够较及时输出。
    environment["PYTHONUNBUFFERED"] = "1"

    return environment


def run_distributed_batch(
    dxc_file_path,
    log_file_path,
):
    """
    调用 ptcdbatch.bat。

    Windows 的 .bat 文件需要通过 cmd.exe /c 执行。
    """
    command = (
        f'"{PTC_DBATCH_BAT}" '
        f'-nographics '
        f'-process '
        f'"{dxc_file_path}"'
    )

    log()
    log("正在启动 Creo Distributed Batch...")
    log("执行命令：")

    visible_command = (
        f'"{PTC_DBATCH_BAT}" '
        f'-nographics '
        f'-process '
        f'"{dxc_file_path}"'
    )

    log(visible_command)
    log()

    process_environment = (
        build_process_environment()
    )

    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=os.path.dirname(PTC_DBATCH_BAT),
        env=process_environment,
        bufsize=1,
        universal_newlines=True,
    )

    output_lines = []

    if process.stdout is not None:
        for output_line in process.stdout:
            output_line = output_line.rstrip(
                "\r\n"
            )

            output_lines.append(output_line)
            log(output_line)

    return_code = process.wait()

    if KEEP_BATCH_LOG:
        os.makedirs(
            os.path.dirname(log_file_path),
            exist_ok=True,
        )

        with open(
            log_file_path,
            "w",
            encoding="utf-8-sig",
            newline="\n",
        ) as log_file:
            log_file.write(
                "Creo Distributed Batch 执行命令\n"
            )
            log_file.write(
                visible_command + "\n\n"
            )

            log_file.write(
                "\n".join(output_lines)
            )

            log_file.write(
                "\n\nReturn code: "
                f"{return_code}\n"
            )

    return return_code, output_lines


# ============================================================
# 输出结果检查
# ============================================================

def find_generated_step_for_model(
    output_folder,
    model,
):
    """
    查找某个模型生成的 STEP 文件。

    先进行确定性同名查找；
    然后进行忽略大小写查找。
    """
    possible_paths = get_possible_step_paths(
        output_folder,
        model,
    )

    for possible_path in possible_paths:
        if (
            os.path.isfile(possible_path)
            and os.path.getsize(possible_path) > 0
        ):
            return possible_path

    target_names = {
        os.path.basename(path).lower()
        for path in possible_paths
    }

    try:
        output_names = os.listdir(
            output_folder
        )
    except OSError:
        return None

    for output_name in output_names:
        if output_name.lower() not in target_names:
            continue

        output_path = os.path.join(
            output_folder,
            output_name,
        )

        if (
            os.path.isfile(output_path)
            and os.path.getsize(output_path) > 0
        ):
            return output_path

    return None


def inspect_conversion_results(
    models,
    output_folder,
):
    """
    检查各模型是否存在对应的非空 STEP 文件。
    """
    successful = []
    missing = []

    for model in models:
        generated_step = (
            find_generated_step_for_model(
                output_folder,
                model,
            )
        )

        result = dict(model)
        result["generated_step"] = (
            generated_step
        )

        if generated_step is None:
            missing.append(result)
        else:
            result["output_size"] = (
                os.path.getsize(
                    generated_step
                )
            )
            successful.append(result)

    return successful, missing


# ============================================================
# 汇总日志
# ============================================================

def write_summary_log(
    summary_file,
    source_folder,
    output_folder,
    models,
    successful,
    missing,
    return_code,
    dxc_file,
):
    """
    写入最终汇总日志。
    """
    lines = []

    lines.append(
        "Creo PRT/ASM 批量转换 STEP 汇总"
    )
    lines.append("=" * 70)
    lines.append(
        f"源文件夹：{source_folder}"
    )
    lines.append(
        f"输出文件夹：{output_folder}"
    )
    lines.append(
        f"DXC 文件：{dxc_file}"
    )
    lines.append(
        f"Distributed Batch 返回码：{return_code}"
    )
    lines.append(
        f"待处理模型数量：{len(models)}"
    )
    lines.append(
        f"检测到 STEP 数量：{len(successful)}"
    )
    lines.append(
        f"未检测到 STEP 数量：{len(missing)}"
    )
    lines.append("")

    if successful:
        lines.append("成功检测到输出的模型：")

        for result in successful:
            lines.append(
                "  [成功] "
                f"{result['file_path']}"
            )
            lines.append(
                "         -> "
                f"{result['generated_step']}"
            )
            lines.append(
                "         文件大小："
                f"{result['output_size']} 字节"
            )

        lines.append("")

    if missing:
        lines.append(
            "没有检测到同名 STEP 的模型："
        )

        for result in missing:
            lines.append(
                "  [需检查] "
                f"{result['file_path']}"
            )

        lines.append("")
        lines.append(
            "缺少同名 STEP 并不一定表示 Creo 完全未导出。"
        )
        lines.append(
            "可能需要检查 Distributed Batch 日志、"
            "实际命名规则、装配依赖或模型打开错误。"
        )

    with open(
        summary_file,
        "w",
        encoding="utf-8-sig",
        newline="\n",
    ) as file_object:
        file_object.write(
            "\n".join(lines)
        )


# ============================================================
# 主程序
# ============================================================

def main():
    """
    主流程。
    """
    log()
    log("=" * 70)
    log("Creo PRT/ASM 批量转换 STEP")
    log("=" * 70)

    dry_run = any(
        argument.lower() == "--dry-run"
        for argument in sys.argv[1:]
    )

    # --------------------------------------------------------
    # 1. 检查 Creo 批处理环境
    # --------------------------------------------------------

    log()
    log("[1/7] 正在检查 Creo Distributed Batch...")

    validate_required_files()

    log(
        f"      ptcdbatch：{PTC_DBATCH_BAT}"
    )
    log(
        f"      STEP TTD ：{STEP_TTD_FILE}"
    )

    if CREO_CONFIG_FILE:
        log(
            f"      config   ：{CREO_CONFIG_FILE}"
        )
    else:
        log(
            "      config   ：未指定"
        )

    # --------------------------------------------------------
    # 2. 选择源文件夹
    # --------------------------------------------------------

    log()
    log("[2/7] 正在获取源文件夹...")

    source_folder = get_input_folder()

    log(f"      源文件夹：{source_folder}")

    # --------------------------------------------------------
    # 3. 扫描 PRT/ASM
    # --------------------------------------------------------

    log()
    log("[3/7] 正在扫描 Creo 模型...")

    models = collect_creo_files(
        source_folder
    )

    if not models:
        raise RuntimeError(
            "选择的文件夹中没有找到可处理的 "
            "PRT/ASM 文件。"
        )

    part_count = sum(
        1
        for model in models
        if model["model_type"] == "prt"
    )

    assembly_count = sum(
        1
        for model in models
        if model["model_type"] == "asm"
    )

    log(
        f"      选中模型总数：{len(models)}"
    )
    log(f"      PRT 数量：{part_count}")
    log(f"      ASM 数量：{assembly_count}")
    log(
        f"      仅最高版本："
        f"{ONLY_LATEST_VERSION}"
    )

    log()
    log("      待转换模型：")

    for index, model in enumerate(
        models,
        start=1,
    ):
        if model["has_version"]:
            version_text = (
                f"版本 {model['version']}"
            )
        else:
            version_text = "无数字版本号"

        log(
            f"      {index:>4}. "
            f"{model['file_path']} "
            f"[{version_text}]"
        )

    # --------------------------------------------------------
    # 4. 创建输出目录和工作目录
    # --------------------------------------------------------

    log()
    log("[4/7] 正在创建输出目录...")

    output_folder = os.path.join(
        source_folder,
        OUTPUT_FOLDER_NAME,
    )

    work_folder = os.path.join(
        output_folder,
        WORK_FOLDER_NAME,
    )

    os.makedirs(
        output_folder,
        exist_ok=True,
    )

    os.makedirs(
        work_folder,
        exist_ok=True,
    )

    log(f"      STEP 输出：{output_folder}")
    log(f"      工作目录：{work_folder}")

    removed_files = (
        remove_existing_step_outputs(
            output_folder,
            models,
        )
    )

    if removed_files:
        log(
            f"      已删除旧 STEP："
            f"{len(removed_files)} 个"
        )

    # --------------------------------------------------------
    # 5. 生成 DXC
    # --------------------------------------------------------

    log()
    log("[5/7] 正在生成 DXC 任务文件...")

    time_stamp = time.strftime(
        "%Y%m%d_%H%M%S"
    )

    dxc_file_path = os.path.join(
        work_folder,
        f"step_export_{time_stamp}.dxc",
    )

    batch_log_path = os.path.join(
        work_folder,
        f"step_export_{time_stamp}.log",
    )

    summary_log_path = os.path.join(
        work_folder,
        f"step_export_{time_stamp}_summary.txt",
    )

    create_dxc_file(
        models=models,
        output_folder=output_folder,
        dxc_file_path=dxc_file_path,
    )

    log(f"      DXC：{dxc_file_path}")

    if dry_run:
        log()
        log("=" * 70)
        log("Dry-run 已完成")
        log("只生成了 DXC，没有启动 Creo。")
        log(f"DXC 文件：{dxc_file_path}")
        log("=" * 70)
        return

    # --------------------------------------------------------
    # 6. 执行 Distributed Batch
    # --------------------------------------------------------

    log()
    log("[6/7] 正在调用 Creo Distributed Batch...")

    return_code, _ = run_distributed_batch(
        dxc_file_path=dxc_file_path,
        log_file_path=batch_log_path,
    )

    log()
    log(
        "      Distributed Batch 返回码："
        f"{return_code}"
    )

    # --------------------------------------------------------
    # 7. 检查转换结果
    # --------------------------------------------------------

    log()
    log("[7/7] 正在检查 STEP 输出...")

    successful, missing = (
        inspect_conversion_results(
            models=models,
            output_folder=output_folder,
        )
    )

    write_summary_log(
        summary_file=summary_log_path,
        source_folder=source_folder,
        output_folder=output_folder,
        models=models,
        successful=successful,
        missing=missing,
        return_code=return_code,
        dxc_file=dxc_file_path,
    )

    log()
    log("=" * 70)
    log("批量任务执行完成")
    log("=" * 70)
    log(f"待转换模型：{len(models)}")
    log(f"检测到 STEP：{len(successful)}")
    log(f"未检测到 STEP：{len(missing)}")
    log(f"返回码：{return_code}")
    log(f"STEP 文件夹：{output_folder}")
    log(f"完整日志：{batch_log_path}")
    log(f"汇总日志：{summary_log_path}")

    if missing:
        log()
        log("以下模型未检测到同名 STEP：")

        for result in missing:
            log(
                f"  [需检查] {result['file_path']}"
            )

    if (
        not KEEP_DXC_FILE
        and os.path.isfile(dxc_file_path)
    ):
        os.remove(dxc_file_path)

    log("=" * 70)

    # 不仅依赖返回码，也检查实际结果。
    if not successful:
        raise RuntimeError(
            "没有检测到任何有效 STEP 输出。"
            "请检查 DXC 和 Distributed Batch 日志。"
        )


# ============================================================
# 程序入口
# ============================================================

if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        log()
        log("=" * 70)
        log("程序执行失败")
        log("=" * 70)
        log(str(error))
        log()

        traceback.print_exc()
        sys.exit(1)