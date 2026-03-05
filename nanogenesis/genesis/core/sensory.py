"""
Genesis V2 Sensory Cortex (感知皮层)
Responsible for ingesting, standardizing, and pre-processing multimodal inputs.

[Architecture]
Raw Input (Discord/Web) -> SensoryCortex -> SensoryPacket -> Manager

This layer handles:
1. File type detection
2. Automatic lightweight pre-processing (OCR, Metadata extraction)
3. Conversion to standardized SensoryItems
"""

import mimetypes
import logging
from pathlib import Path
from typing import List, Union, Optional, Any
from genesis.core.contracts import SensoryItem, SensoryPacket

logger = logging.getLogger(__name__)

class SensoryCortex:
    """
    The sensory gateway for Genesis.
    Transforms raw paths/bytes/strings into a structured SensoryPacket.
    """

    def __init__(self):
        # We can register processors here (OCR, Transcribe, etc.)
        pass

    async def perceive(self, 
                 text_input: str, 
                 attachments: List[str] = None, 
                 source: str = "unknown",
                 context_id: str = "") -> SensoryPacket:
        """
        Main entry point to construct a SensoryPacket.
        
        Args:
            text_input: The user's text message.
            attachments: List of file paths (absolute).
            source: Input source (e.g. 'discord').
        """
        items = []

        # 1. Process Text
        if text_input and text_input.strip():
            items.append(SensoryItem(
                type="text",
                content=text_input.strip(),
                mime_type="text/plain"
            ))

        # 2. Process Attachments
        if attachments:
            for path_str in attachments:
                item = await self._process_file(path_str)
                if item:
                    items.append(item)

        return SensoryPacket(items=items, source=source, context_id=context_id)

    async def _process_file(self, path_str: str) -> Optional[SensoryItem]:
        path = Path(path_str)
        if not path.exists():
            logger.warning(f"Sensory input file not found: {path}")
            return None

        mime_type, _ = mimetypes.guess_type(path)
        mime_type = mime_type or "application/octet-stream"
        
        # Determine modality type
        if mime_type.startswith("image/"):
            modality = "image"
            metadata = await self._quick_scan_image(path)
        elif mime_type.startswith("audio/"):
            modality = "audio"
            metadata = {"duration": "unknown"} # Placeholder for audio scan
        elif mime_type.startswith("text/") or path.suffix in ['.py', '.md', '.txt', '.json']:
            modality = "file" # Treated as a readable file, not raw text instruction
            metadata = {}
        else:
            modality = "file"
            metadata = {}

        return SensoryItem(
            type=modality,
            content=str(path.absolute()),
            mime_type=mime_type,
            metadata=metadata
        )

    async def _quick_scan_image(self, path: Path) -> dict:
        """
        Lightweight pre-processing for images.
        We do NOT run heavy OCR here by default to keep latency low, 
        unless configured to do 'active perception'.
        For now, we just extract basic dimensions.
        """
        meta = {}
        try:
            from PIL import Image
            with Image.open(path) as img:
                meta["size"] = img.size
                meta["format"] = img.format
                meta["mode"] = img.mode
        except ImportError:
            pass # Pillow not installed
        except Exception as e:
            logger.warning(f"Failed to scan image {path}: {e}")
        return meta
