import base64
from pathlib import Path

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def build_multimodal_content(text, image_paths):
    content = [{"type": "text", "text": text}]
    for path in image_paths:
        try:
            base64_img = encode_image(path)
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_img}"
                }
            })
        except Exception as e:
            print(f"Failed to encode {path}: {e}")
    return content

print("Test Vision builder ready")
