#!/usr/bin/env python3
"""
MongoDB Admin TUI - Terminal User Interface for MongoDB management

使用方法:
    python scripts/mongodb_admin_tui.py
    或
    PYTHONPATH=. python scripts/mongodb_admin_tui.py

界面布局:
    ┌─────────────────────────────────────────┐
    │  MongoDB Admin - astrometry_dev        │
    ├──────────┬──────────────────────────────┤
    │          │                              │
    │ Collections│  Documents Table           │
    │ 📊 api_keys│  ┌──────────────────────┐  │
    │ 📊 jobs   │  │ _id │ 字段预览        │  │
    │ 📊 queue  │  │ ... │ ...            │  │
    │          │  └──────────────────────┘  │
    │          │                              │
    │          │  Document Detail (底部)      │
    │          │  ┌──────────────────────┐  │
    │          │  │ { JSON 详情 }       │  │
    │          │  └──────────────────────┘  │
    └──────────┴──────────────────────────────┘

快捷键:
    ↑↓        - 导航集合/文档列表
    Enter     - 查看文档详情（自动显示）
    Tab       - 在集合列表和文档表格间切换焦点
    r         - 刷新当前集合的文档列表
    d         - 删除当前文档（需确认）
    Ctrl+Shift+R - 重置数据库（需确认文本输入）
    q         - 退出

功能说明:
    1. 左侧显示所有 MongoDB 集合及其文档数量
    2. 选择集合后，中间显示该集合的文档列表
    3. 选择文档后，底部自动显示完整的 JSON 详情
    4. 删除和重置功能已禁用，需要修改代码中的注释来启用

安全提示:
    - 删除和重置功能默认禁用，防止误操作
    - 如需启用，请修改代码中相应的注释部分
    - 建议在生产环境中谨慎使用这些功能
"""

import shutil
from pathlib import Path
from typing import Any, Optional

from astropy.io import fits
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales
from bson.json_util import dumps, default
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    TextArea,
)

from core.config import settings
from domain.enums import ArtifactType
from services.mongo import create_mongo_client, get_database


class CollectionList(ListView):
    """左侧集合列表"""

    BINDINGS = [
        Binding("up", "cursor_up", "上移", show=False),
        Binding("down", "cursor_down", "下移", show=False),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.collections: list[dict[str, Any]] = []

    async def load_collections(self, db) -> None:
        """加载集合列表"""
        collections = await db.list_collection_names()
        self.collections = []
        for col_name in sorted(collections):
            count = await db[col_name].count_documents({})
            self.collections.append({"name": col_name, "count": count})
            self.append(ListItem(Label(f"📊 {col_name:20s} ({count:6d})")))

    def get_selected_collection(self) -> Optional[str]:
        """获取当前选中的集合名称"""
        try:
            # ListView 使用 index 属性来获取当前选中的索引
            if hasattr(self, 'index') and self.index is not None:
                index = self.index
                if 0 <= index < len(self.collections):
                    return self.collections[index].get("name")
        except (AttributeError, IndexError, TypeError):
            pass
        return None


class DocumentTable(DataTable):
    """中间文档表格"""

    BINDINGS = [
        Binding("up", "cursor_up", "上移", show=False),
        Binding("down", "cursor_down", "下移", show=False),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.documents: list[dict[str, Any]] = []
        self.columns_added = False

    def clear_table(self) -> None:
        """清空表格"""
        self.clear(columns=True)  # 同时清除列
        self.documents = []
        self.columns_added = False

    async def load_documents(self, db, collection_name: str, limit: int = 100) -> None:
        """加载文档列表"""
        # 先清除表格（包括列）
        self.clear(columns=True)
        self.documents = []
        self.columns_added = False

        # 添加两列：ID 和文档内容
        self.add_column("ID", width=26)
        self.add_column("文档内容", width=None)  # 自动宽度
        self.columns_added = True

        # 查询文档
        cursor = db[collection_name].find({}).limit(limit).sort("_id", -1)
        async for doc in cursor:
            self.documents.append(doc)
            # 分离 ID 和内容预览
            doc_id = str(doc.get("_id", ""))[:24]
            preview = self._format_preview(doc)
            self.add_row(doc_id, preview)

    def _format_preview(self, doc: dict[str, Any]) -> str:
        """格式化文档预览 - 简化版本（不包含 ID）"""
        # 收集前几个简单字段的值（跳过复杂的嵌套结构和 _id）
        preview_parts = []
        field_count = 0
        max_fields = 3  # 最多显示3个字段
        
        for key, value in doc.items():
            if key == "_id":
                continue  # ID 已经在单独的列显示了
            
            # 只显示简单的值类型
            if isinstance(value, (str, int, float, bool)):
                # 限制字符串长度
                if isinstance(value, str) and len(value) > 30:
                    value_str = value[:27] + "..."
                else:
                    value_str = str(value)
                preview_parts.append(f"{key}: {value_str}")
                field_count += 1
            elif isinstance(value, list):
                preview_parts.append(f"{key}: [{len(value)} items]")
                field_count += 1
            elif isinstance(value, dict):
                preview_parts.append(f"{key}: {{...}}")
                field_count += 1
            
            if field_count >= max_fields:
                break
        
        # 返回字段预览
        if preview_parts:
            return " | ".join(preview_parts)
        else:
            return "(空文档)"

    def get_selected_document(self) -> Optional[dict[str, Any]]:
        """获取当前选中的文档"""
        if self.cursor_row is not None and self.documents:
            return self.documents[self.cursor_row]
        return None


class DocumentDetail(TextArea):
    """底部文档详情显示"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.read_only = True
        self.current_collection: Optional[str] = None

    def set_collection(self, collection_name: Optional[str]) -> None:
        """设置当前集合名称"""
        self.current_collection = collection_name

    def show_document(self, doc: dict[str, Any]) -> None:
        """显示文档详情"""
        # 如果是 artifacts 集合，尝试解析文件信息
        if self.current_collection == "artifacts":
            doc_with_file_info = self._enrich_artifact_doc(doc)
            
            # 提取预览信息（如果存在）
            ascii_preview = None
            wcs_preview = None
            file_info = doc_with_file_info.get("_file_info", {})
            if isinstance(file_info, dict):
                ascii_preview = file_info.pop("ascii_preview", None)
                wcs_preview = file_info.pop("wcs_preview", None)
            
            json_str = dumps(doc_with_file_info, indent=2, ensure_ascii=False, default=default)
            
            # 添加预览信息
            preview_parts = []
            if wcs_preview:
                preview_parts.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nWCS 预览:\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{wcs_preview}")
            if ascii_preview:
                preview_parts.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n图片预览 (ASCII):\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n{ascii_preview}")
            
            if preview_parts:
                json_str = f"{json_str}\n\n" + "\n\n".join(preview_parts)
        else:
            # 格式化 JSON
            json_str = dumps(doc, indent=2, ensure_ascii=False, default=default)
        self.text = json_str

    def _enrich_artifact_doc(self, doc: dict[str, Any]) -> dict[str, Any]:
        """为 artifacts 文档添加文件信息"""
        doc_copy = doc.copy()
        path_str = doc.get("path")
        artifact_type_str = doc.get("artifact_type")
        
        if not path_str:
            return doc_copy
        
        file_path = Path(path_str)
        
        # 如果路径是相对路径，尝试基于项目根目录解析
        if not file_path.is_absolute():
            # 尝试相对于项目根目录（当前工作目录）
            # artifacts 路径通常是相对于项目根目录的，如 "./data/jobs/123/wcs.fits"
            if str(file_path).startswith("./"):
                # 移除开头的 "./"
                file_path = Path.cwd() / str(file_path)[2:]
            else:
                # 尝试相对于当前工作目录
                file_path = Path.cwd() / file_path
        
        if not file_path.exists():
            doc_copy["_file_info"] = {
                "exists": False,
                "error": f"文件不存在: {file_path}"
            }
            return doc_copy
        
        # 获取文件基本信息
        file_info: dict[str, Any] = {
            "exists": True,
            "path": str(file_path),
            "size_bytes": file_path.stat().st_size,
            "size_human": self._format_size(file_path.stat().st_size),
        }
        
        # 根据 artifact_type 解析特定信息
        try:
            if artifact_type_str in ["wcs", "new_fits"]:
                # 解析 FITS/WCS 文件
                fits_info = self._parse_fits_file(file_path)
                if fits_info:
                    file_info["fits_info"] = fits_info
                
                # 如果是 WCS 文件，尝试生成可视化预览
                if artifact_type_str == "wcs":
                    wcs_preview = self._generate_wcs_preview(file_path)
                    if wcs_preview:
                        file_info["wcs_preview"] = wcs_preview
            elif artifact_type_str == "annotated":
                # 解析图像文件
                from PIL import Image
                try:
                    img = Image.open(file_path)
                    file_info["image_info"] = {
                        "format": img.format,
                        "mode": img.mode,
                        "size": f"{img.width}x{img.height}",
                        "width": img.width,
                        "height": img.height,
                    }
                    # 生成 ASCII 预览
                    ascii_preview = self._image_to_ascii(file_path)
                    if ascii_preview:
                        file_info["ascii_preview"] = ascii_preview
                except Exception as e:
                    file_info["image_info"] = {"error": str(e)}
        except Exception as e:
            file_info["parse_error"] = str(e)
        
        doc_copy["_file_info"] = file_info
        return doc_copy

    def _parse_fits_file(self, file_path: Path) -> Optional[dict[str, Any]]:
        """解析 FITS 文件，提取 WCS 信息"""
        try:
            with fits.open(file_path) as hdul:
                header = hdul[0].header
                
                fits_info: dict[str, Any] = {
                    "naxis": {
                        "naxis1": header.get("NAXIS1"),
                        "naxis2": header.get("NAXIS2"),
                    },
                }
                
                # 尝试解析 WCS
                try:
                    wcs = WCS(header)
                    if wcs.is_celestial:
                        # 计算中心坐标
                        naxis1 = header.get("NAXIS1", 0)
                        naxis2 = header.get("NAXIS2", 0)
                        if naxis1 and naxis2:
                            center = wcs.pixel_to_world(naxis1 / 2, naxis2 / 2)
                            scales = proj_plane_pixel_scales(wcs)
                            pixscale_arcsec = float(scales.mean() * 3600)
                            
                            fits_info["wcs"] = {
                                "center": {
                                    "ra_deg": round(float(center.ra.deg), 6),
                                    "dec_deg": round(float(center.dec.deg), 6),
                                    "ra_hms": str(center.ra.to_string(unit="hour", precision=1)),
                                    "dec_dms": str(center.dec.to_string(unit="deg", precision=1)),
                                },
                                "pixscale_arcsec": round(pixscale_arcsec, 3),
                            }
                            
                            # 添加一些关键的 FITS 头信息
                            for key in ["CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2", "CD1_1", "CD1_2", "CD2_1", "CD2_2"]:
                                if key in header:
                                    if "header_keys" not in fits_info:
                                        fits_info["header_keys"] = {}
                                    value = header[key]
                                    if isinstance(value, (int, float)):
                                        fits_info["header_keys"][key] = round(float(value), 6) if isinstance(value, float) else value
                                    else:
                                        fits_info["header_keys"][key] = str(value)
                except Exception as e:
                    fits_info["wcs_error"] = str(e)
                
                return fits_info
        except Exception as e:
            return {"error": str(e)}

    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    def _image_to_ascii(self, image_path: Path, width: int = 60, height: int = 20) -> Optional[str]:
        """将图片转换为 ASCII 艺术预览"""
        try:
            from PIL import Image
            
            # 打开并调整图片大小
            img = Image.open(image_path)
            
            # 转换为 RGB（如果是 RGBA 或其他格式）
            if img.mode != "RGB":
                img = img.convert("RGB")
            
            # 保持宽高比缩放
            img_width, img_height = img.size
            aspect_ratio = img_width / img_height
            if aspect_ratio > width / height:
                new_width = width
                new_height = int(width / aspect_ratio)
            else:
                new_height = height
                new_width = int(height * aspect_ratio)
            
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # 转换为灰度
            img_gray = img.convert("L")
            
            # ASCII 字符集（从暗到亮）
            # 使用 Unicode 块字符获得更好的效果
            ascii_chars = " ░▒▓█"
            # 或者使用更简单的字符集：ascii_chars = " .:-=+*#%@"
            
            # 转换为 ASCII
            ascii_lines = []
            pixels = img_gray.load()
            
            for y in range(new_height):
                line = ""
                for x in range(new_width):
                    brightness = pixels[x, y]
                    # 将亮度值 (0-255) 映射到字符索引 (0-4)
                    char_index = int(brightness / 255 * (len(ascii_chars) - 1))
                    line += ascii_chars[char_index] * 2  # 每个字符显示两次，因为终端字符通常比较窄
                ascii_lines.append(line)
            
            return "\n".join(ascii_lines)
        except Exception as e:
            return None

    def _generate_wcs_preview(self, wcs_path: Path) -> Optional[str]:
        """生成 WCS 文件的可视化预览"""
        try:
            with fits.open(wcs_path) as hdul:
                header = hdul[0].header
                wcs = WCS(header)
                
                if not wcs.is_celestial:
                    return None
                
                naxis1 = header.get("NAXIS1", 0)
                naxis2 = header.get("NAXIS2", 0)
                if not naxis1 or not naxis2:
                    return None
                
                # 计算四个角的坐标
                corners = [
                    (0, 0),           # 左下
                    (naxis1, 0),      # 右下
                    (naxis1, naxis2), # 右上
                    (0, naxis2),      # 左上
                ]
                
                corner_coords = []
                for x, y in corners:
                    coord = wcs.pixel_to_world(x, y)
                    corner_coords.append({
                        "pixel": f"({x}, {y})",
                        "ra_deg": round(float(coord.ra.deg), 6),
                        "dec_deg": round(float(coord.dec.deg), 6),
                        "ra_hms": str(coord.ra.to_string(unit="hour", precision=1)),
                        "dec_dms": str(coord.dec.to_string(unit="deg", precision=1)),
                    })
                
                # 计算中心坐标
                center = wcs.pixel_to_world(naxis1 / 2, naxis2 / 2)
                scales = proj_plane_pixel_scales(wcs)
                pixscale_arcsec = float(scales.mean() * 3600)
                
                # 生成预览文本
                preview_lines = [
                    f"图像尺寸: {naxis1} x {naxis2} 像素",
                    f"像素比例: {pixscale_arcsec:.3f} arcsec/pixel",
                    "",
                    f"中心坐标:",
                    f"  RA:  {center.ra.to_string(unit='hour', precision=2)}  ({center.ra.deg:.6f}°)",
                    f"  Dec: {center.dec.to_string(unit='deg', precision=2)}  ({center.dec.deg:.6f}°)",
                    "",
                    "四个角坐标:",
                ]
                
                corner_labels = ["左下", "右下", "右上", "左上"]
                for i, (label, corner) in enumerate(zip(corner_labels, corner_coords)):
                    preview_lines.append(f"  {label}: {corner['pixel']}")
                    preview_lines.append(f"    RA:  {corner['ra_hms']}  ({corner['ra_deg']:.6f}°)")
                    preview_lines.append(f"    Dec: {corner['dec_dms']}  ({corner['dec_deg']:.6f}°)")
                    if i < len(corner_coords) - 1:
                        preview_lines.append("")
                
                return "\n".join(preview_lines)
        except Exception as e:
            return None


class ConfirmDialog(ModalScreen[bool]):
    """确认对话框 - 用于删除单个文档等操作"""

    CSS = """
    ConfirmDialog {
        align: center middle;
    }
    
    .dialog-container {
        width: 60;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1;
    }
    
    .dialog-title {
        text-style: bold;
        width: 100%;
        text-align: center;
        margin-bottom: 1;
    }
    
    .dialog-message {
        width: 100%;
        margin-bottom: 1;
        padding: 1;
    }
    
    .dialog-buttons {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    """

    def __init__(self, title: str, message: str, **kwargs):
        super().__init__(**kwargs)
        self.dialog_title = title
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(classes="dialog-container"):
            yield Label(self.dialog_title, classes="dialog-title")
            yield Label(self.message, classes="dialog-message")
            with Horizontal(classes="dialog-buttons"):
                yield Button("确认 (y)", variant="error", id="confirm")
                yield Button("取消 (n)", variant="primary", id="cancel")

    @on(Button.Pressed, "#confirm")
    def on_confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#cancel")
    def on_cancel(self) -> None:
        self.dismiss(False)

    def on_key(self, event) -> None:
        """键盘快捷键"""
        if event.key == "y":
            self.dismiss(True)
        elif event.key == "n" or event.key == "escape":
            self.dismiss(False)
        else:
            event.prevent_default()


class InputConfirmDialog(ModalScreen[bool]):
    """输入确认对话框 - 用于重置数据库等危险操作"""

    CSS = """
    InputConfirmDialog {
        align: center middle;
    }
    
    .dialog-container {
        width: 70;
        height: auto;
        border: solid $error;
        background: $surface;
        padding: 1;
    }
    
    .dialog-title {
        text-style: bold;
        color: $error;
        width: 100%;
        text-align: center;
        margin-bottom: 1;
    }
    
    .dialog-message {
        width: 100%;
        margin-bottom: 1;
        padding: 1;
    }
    
    .dialog-input-container {
        width: 100%;
        margin-bottom: 1;
    }
    
    .dialog-input-label {
        width: 100%;
        margin-bottom: 1;
    }
    
    .dialog-input {
        width: 100%;
        margin-bottom: 1;
    }
    
    .dialog-buttons {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    """

    def __init__(self, title: str, message: str, confirm_text: str, **kwargs):
        super().__init__(**kwargs)
        self.dialog_title = title
        self.message = message
        self.confirm_text = confirm_text
        self.input_widget: Optional[Input] = None

    def compose(self) -> ComposeResult:
        with Container(classes="dialog-container"):
            yield Label(self.dialog_title, classes="dialog-title")
            yield Label(self.message, classes="dialog-message")
            yield Label(
                f'请输入 "{self.confirm_text}" 以确认：',
                classes="dialog-input-label"
            )
            self.input_widget = Input(
                placeholder=f'输入 "{self.confirm_text}"',
                classes="dialog-input",
                id="confirm-input"
            )
            yield self.input_widget
            with Horizontal(classes="dialog-buttons"):
                yield Button("执行", variant="error", id="confirm")
                yield Button("取消", variant="primary", id="cancel")

    def on_mount(self) -> None:
        """挂载后聚焦输入框"""
        if self.input_widget:
            self.input_widget.focus()

    @on(Button.Pressed, "#confirm")
    def on_confirm(self) -> None:
        if self.input_widget:
            input_value = self.input_widget.value.strip()
            if input_value == self.confirm_text:
                self.dismiss(True)
            else:
                # 输入不匹配，显示提示但不关闭对话框
                self.input_widget.value = ""
                self.input_widget.placeholder = f'输入不匹配！请输入 "{self.confirm_text}"'

    @on(Button.Pressed, "#cancel")
    def on_cancel(self) -> None:
        self.dismiss(False)

    def on_key(self, event) -> None:
        """键盘快捷键"""
        if event.key == "escape":
            self.dismiss(False)
        elif event.key == "enter" and self.input_widget:
            # Enter 键触发确认
            input_value = self.input_widget.value.strip()
            if input_value == self.confirm_text:
                self.dismiss(True)
            else:
                self.input_widget.value = ""
                self.input_widget.placeholder = f'输入不匹配！请输入 "{self.confirm_text}"'
                event.prevent_default()


class MongoDBAdminApp(App):
    """MongoDB Admin TUI 主应用"""

    CSS = """
    Screen {
        background: $surface;
    }
    
    CollectionList {
        width: 30;
        border: solid $primary;
        background: $panel;
    }
    
    DocumentTable {
        border: solid $primary;
        height: 1fr;  /* 使用 flex 布局，占据剩余空间 */
    }
    
    DocumentDetail {
        height: 15;
        min-height: 10;  /* 最小高度，确保可见 */
        max-height: 20;  /* 最大高度，防止占用太多空间 */
        border: solid $primary;
        background: $panel;
    }
    
    Vertical {
        height: 100%;
    }
    
    Vertical {
        height: 100%;
    }
    
    .status-bar {
        height: 1;
        background: $primary;
        color: $text;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("h", "show_help", "帮助"),
        Binding("r", "refresh", "刷新"),
        Binding("d", "delete_document", "删除文档"),
        Binding("ctrl+shift+r", "reset_database", "重置数据库"),
        Binding("/", "search", "搜索"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.client = None
        self.db = None
        self.current_collection: Optional[str] = None

    async def on_mount(self) -> None:
        """应用启动时初始化"""
        # 连接 MongoDB
        self.client = create_mongo_client()
        self.db = get_database(self.client)
        
        # 加载集合列表
        collection_list = self.query_one(CollectionList)
        await collection_list.load_collections(self.db)
        
        # 静默启动，不显示提示

    async def on_unmount(self) -> None:
        """应用退出时清理"""
        if self.client:
            self.client.close()

    def compose(self) -> ComposeResult:
        """构建 UI"""
        yield Header(show_clock=True)
        with Horizontal():
            yield CollectionList(id="collection_list")
            with Vertical():
                yield DocumentTable(id="document_table")
                yield DocumentDetail(id="document_detail")
        yield Footer()

    @on(ListView.Selected, "#collection_list")
    async def on_collection_selected(self, event: ListView.Selected) -> None:
        """集合选择变化时加载文档"""
        await self.load_collection_documents()

    @on(ListView.Highlighted, "#collection_list")
    async def on_collection_highlighted(self, event: ListView.Highlighted) -> None:
        """集合高亮变化时自动加载文档"""
        # 当用户用箭头键导航时，自动加载文档
        await self.load_collection_documents()

    async def load_collection_documents(self) -> None:
        """加载当前选中集合的文档"""
        collection_list = self.query_one(CollectionList)
        collection_name = collection_list.get_selected_collection()
        if collection_name and collection_name != self.current_collection:
            self.current_collection = collection_name
            document_table = self.query_one(DocumentTable)
            try:
                await document_table.load_documents(self.db, collection_name)
            except Exception as e:
                # 只在出错时显示通知
                self.notify(f"✗ 加载失败: {e}", timeout=3)

    @on(DataTable.RowSelected, "#document_table")
    async def on_document_selected(self, event: DataTable.RowSelected) -> None:
        """文档选择变化时显示详情"""
        await self.show_document_detail()
    
    @on(DataTable.RowHighlighted, "#document_table")
    async def on_document_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """文档高亮变化时自动显示详情（用箭头键导航时）"""
        await self.show_document_detail()
    
    @on(DataTable.CellSelected, "#document_table")
    async def on_document_cell_selected(self, event: DataTable.CellSelected) -> None:
        """文档单元格选择时显示详情"""
        await self.show_document_detail()
    
    async def show_document_detail(self) -> None:
        """显示当前选中文档的详情"""
        document_table = self.query_one(DocumentTable)
        doc = document_table.get_selected_document()
        if doc:
            document_detail = self.query_one(DocumentDetail)
            # 设置当前集合名称，用于判断是否需要解析文件
            document_detail.set_collection(self.current_collection)
            document_detail.show_document(doc)
        else:
            # 如果没有选中文档，清空详情显示
            document_detail = self.query_one(DocumentDetail)
            document_detail.text = ""

    @work(exclusive=True)
    async def action_delete_document(self) -> None:
        """删除当前文档"""
        if not self.current_collection:
            self.notify("请先选择一个集合", timeout=2)
            return

        document_table = self.query_one(DocumentTable)
        doc = document_table.get_selected_document()
        if not doc:
            self.notify("请先选择一个文档", timeout=2)
            return

        doc_id = doc.get("_id")
        if not doc_id:
            return

        # 准备确认消息
        doc_id_str = str(doc_id)[:24]
        # 尝试显示一些关键字段用于确认
        preview_fields = []
        for key in ["job_id", "api_key", "original_filename", "name"]:
            if key in doc:
                value = str(doc[key])
                if len(value) > 30:
                    value = value[:27] + "..."
                preview_fields.append(f"{key}: {value}")
                if len(preview_fields) >= 2:
                    break
        
        preview_text = "\n".join(preview_fields) if preview_fields else "(无关键字段)"
        message = (
            f"确定要删除此文档吗？\n\n"
            f"_id: {doc_id_str}\n"
            f"{preview_text}\n\n"
            f"⚠️  此操作不可撤销！"
        )

        # 显示确认对话框
        confirmed = await self.confirm_dialog("确认删除文档", message)
        
        if not confirmed:
            return

        # 执行删除
        try:
            await self.db[self.current_collection].delete_one({"_id": doc_id})
            self.notify(f"✓ 已删除文档: {doc_id_str}", timeout=2)
            
            # 重新加载文档列表
            await document_table.load_documents(self.db, self.current_collection)
            
            # 清空详情显示
            document_detail = self.query_one(DocumentDetail)
            document_detail.text = ""
            
        except Exception as e:
            self.notify(f"✗ 删除失败: {e}", timeout=3)

    @work(exclusive=True)
    async def action_reset_database(self) -> None:
        """重置数据库"""
        # 显示警告
        self.update_status(
            "⚠️  重置数据库是危险操作！"
            "这将删除所有数据。"
            "请修改代码以启用此功能。"
        )
        
        # 安全起见，暂时禁用自动重置
        # 取消下面的注释以启用重置功能
        # try:
        #     self.update_status("正在重置数据库...")
        #     
        #     # 1. 删除所有集合
        #     collections = await self.db.list_collection_names()
        #     for col_name in collections:
        #         await self.db[col_name].delete_many({})
        #     
        #     # 2. 删除文件系统
        #     jobs_dir = settings.job_output_dir
        #     if jobs_dir.exists():
        #         for job_dir in jobs_dir.iterdir():
        #             if job_dir.is_dir():
        #                 shutil.rmtree(job_dir)
        #     
        #     uploads_dir = settings.upload_cache_dir
        #     if uploads_dir.exists():
        #         for upload_file in uploads_dir.iterdir():
        #             if upload_file.is_file():
        #                 upload_file.unlink()
        #     
        #     self.update_status("✓ 数据库已重置")
        #     
        #     collection_list = self.query_one(CollectionList)
        #     await collection_list.load_collections(self.db)
        #     
        # except Exception as e:
        #     self.update_status(f"✗ 重置失败: {e}")

    async def confirm_dialog(self, title: str, message: str) -> bool:
        """确认对话框"""
        dialog = ConfirmDialog(title, message)
        result = await self.push_screen_wait(dialog)
        return result if result is not None else False

    async def input_confirm_dialog(
        self, title: str, message: str, confirm_text: str
    ) -> bool:
        """输入确认对话框 - 用于危险操作"""
        dialog = InputConfirmDialog(title, message, confirm_text)
        result = await self.push_screen_wait(dialog)
        return result if result is not None else False

    def update_status(self, message: str) -> None:
        """更新状态栏"""
        footer = self.query_one(Footer)
        # Footer 不直接支持设置文本，我们使用 title 属性或者通过其他方式
        # 简化处理：使用 notify 显示消息
        self.notify(message, timeout=3)

    @work(exclusive=True)
    async def action_refresh(self) -> None:
        """刷新当前集合的文档列表"""
        if not self.current_collection:
            self.notify("请先选择一个集合", timeout=2)
            return
        
        document_table = self.query_one(DocumentTable)
        try:
            await document_table.load_documents(self.db, self.current_collection)
            doc_count = len(document_table.documents)
            self.notify(f"✓ 已刷新 {self.current_collection}: {doc_count} 条文档", timeout=2)
            
            # 清空详情显示
            document_detail = self.query_one(DocumentDetail)
            document_detail.text = ""
        except Exception as e:
            self.notify(f"✗ 刷新失败: {e}", timeout=3)
    
    def action_search(self) -> None:
        """搜索功能（待实现）"""
        self.update_status("搜索功能待实现")
    
    def action_show_help(self) -> None:
        """显示帮助信息"""
        help_text = (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "  MongoDB Admin TUI - 帮助\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "【导航快捷键】\n"
            "  ↑↓        在集合列表或文档列表中上下导航\n"
            "  Tab       在集合列表和文档表格之间切换焦点\n"
            "  Enter     选择集合（在集合列表中）\n\n"
            "【查看操作】\n"
            "  选择集合后，文档会自动加载到中间表格\n"
            "  选择文档后，详情会自动显示在底部\n\n"
            "【功能快捷键】\n"
            "  h         显示此帮助信息\n"
            "  r         刷新当前集合的文档列表\n"
            "  d         删除当前文档（需确认）\n"
            "  Ctrl+Shift+R  重置数据库（需确认文本输入）\n"
            "  /         搜索（待实现）\n"
            "  q         退出应用\n\n"
            "【操作流程】\n"
            "  1. 用 ↑↓ 键选择集合 → 自动加载文档\n"
            "  2. 按 Tab 切换到文档表格 → 用 ↑↓ 选择文档\n"
            "  3. 选中文档后 → 底部自动显示 JSON 详情\n\n"
            "【提示】\n"
            "  • 删除文档会显示确认对话框，按 y 确认或 n 取消\n"
            "  • 重置数据库需要输入确认文本，防止误操作"
        )
        self.notify(help_text, timeout=20, severity="information")


def main():
    """主函数"""
    app = MongoDBAdminApp()
    app.run()


if __name__ == "__main__":
    main()

