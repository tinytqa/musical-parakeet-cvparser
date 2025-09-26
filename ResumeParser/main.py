import os
from pathlib import Path

from text_extraction import extract_text_from_file 
from typing import List, Optional
import json
    

def main():
    # Đường dẫn file test (có thể là DOCX hoặc PDF)
    test_file = "C:/Users/tranq/Downloads/final-de-cuong-nnpldc.pdf"
    
    # Đọc file bytes
    with open(test_file, "rb") as f:
        file_bytes = f.read()
    
    # Gọi hàm extract_text_from_file
    try:
        extracted_text = extract_text_from_file(
            file_bytes=file_bytes,
            filename=test_file,
            postprocess=True,
            to_json=False
        )
        print("=== Extracted Text ===")
        print(extracted_text[:500])  # in thử 500 ký tự đầu

        # Đặt tên folder
        folder_name = "cv"
        output_dir = os.path.join("output", folder_name)
        os.makedirs(output_dir, exist_ok=True)

        # Lưu ra .md
        path = Path(test_file)
        output_md_path = os.path.join(output_dir, f"{path.stem}.md")
        with open(output_md_path, "w", encoding="utf-8") as f:
            f.write(extracted_text)

        print(f"\n✅ Done! Kết quả đầy đủ đã được lưu trong: {output_md_path}")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
