# main.py
import requests
import fitz  # PyMuPDF
from PIL import Image
import io
import os
import json
import google.generativeai as genai
from dotenv import load_dotenv


# --- ค่าคงที่และตัวแปร ---
# ID ของไฟล์จาก Google Drive URL
GDRIVE_FILE_ID = "1vgPWpEudd0U6zE60BIPlEDadsPx1ZSQ8"
PDF_FILENAME = "downloaded_po.pdf"
JSON_OUTPUT_FILENAME = "output.json"

def download_gdrive_file(file_id, destination):
    """ดาวน์โหลดไฟล์สาธารณะจาก Google Drive"""
    URL = f"https://drive.google.com/uc?export=download&id={file_id}"
    print(f"กำลังดาวน์โหลดไฟล์ PDF จาก Google Drive...")
    response = requests.get(URL, stream=True)
    if response.status_code == 200:
        with open(destination, "wb") as f:
            for chunk in response.iter_content(32768):
                if chunk:
                    f.write(chunk)
        print(f"ดาวน์โหลดไฟล์สำเร็จ บันทึกเป็น: {destination}")
        return True
    else:
        print(f"ดาวน์โหลดไฟล์ล้มเหลว Status code: {response.status_code}")
        return False

def convert_pdf_to_images(pdf_path):
    """แปลงแต่ละหน้าของ PDF เป็นอ็อบเจกต์รูปภาพของ PIL"""
    doc = fitz.open(pdf_path)
    pil_images = []
    print(f"กำลังแปลงไฟล์ PDF จำนวน {len(doc)} หน้า เป็นรูปภาพ...")
    for page in doc:
        pix = page.get_pixmap(dpi=200) # เพิ่มความละเอียดเพื่อให้ AI อ่านง่ายขึ้น
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        pil_images.append(img)
    doc.close()
    print("แปลงเป็นรูปภาพสำเร็จ")
    return pil_images

def analyze_images_with_gemini(images, prompt):
    """ส่งรูปภาพและ Prompt ไปให้ Gemini วิเคราะห์"""
    print("กำลังส่งข้อมูลให้ Gemini API วิเคราะห์...")
    model = genai.GenerativeModel('gemini-2.0-flash') # หรือ gemini-pro-vision  gemini-1.5-flash-latest
    
    # สร้าง content ที่จะส่งไป โดยใส่ prompt ก่อนแล้วตามด้วยรูปภาพทั้งหมด
    content_parts = [prompt] + images
    
    try:
        response = model.generate_content(content_parts)
        # ทำความสะอาดผลลัพธ์ที่อาจมี ```json ... ``` ครอบอยู่
        cleaned_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        return cleaned_text
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการเรียกใช้ Gemini API: {e}")
        return None

def main():
    """ฟังก์ชันหลักในการทำงานทั้งหมด"""
    # โหลด API Key จากไฟล์ .env
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("ไม่พบ GOOGLE_API_KEY ในไฟล์ .env")
        return
    genai.configure(api_key=api_key)

    if not download_gdrive_file(GDRIVE_FILE_ID, PDF_FILENAME):
        return

    images = convert_pdf_to_images(PDF_FILENAME)

    # สร้าง Prompt ที่ระบุข้อมูลที่ต้องการอย่างละเอียด
    extraction_prompt = """
    คุณคือผู้เชี่ยวชาญด้านการดึงข้อมูลจากเอกสารทางธุรกิจ
    จากรูปภาพให้หาเอกสารที่ขึ้นต้นหัวกระดาษว่า ใบรับ / วางบิล ที่แนบมานี้ โปรดดึงข้อมูลใน PDF หน้า 1 เสมอ ออกมาและจัดให้อยู่ในรูปแบบ JSON ที่ถูกต้องเท่านั้น:

    1.  `company_info`: ข้อมูลบริษัทที่อยู่บนหัวกระดาษของหน้าที่ 1
        -   `supplier No.`: ชื่อบริษัท
        -   `address supplier`: ที่อยู่ทั้งหมด
        -   `tax_id`: เลขประจำตัวผู้เสียภาษี
    2.  `po_number`: หมายเลข PO ที่ระบุในเอกสาร
    3.  `payment term`: จำนวนวัน
    4.  `items`: รายการสินค้าทั้งหมด โดยแต่ละรายการให้มีข้อมูลดังนี้
        -   `item_number`: หมายเลข Item
        -   `Receipt Qty`: จำนวนรับ
        -   `Oder Unit`: หน่วยนับ (เช่น EA)
        -   `Location`: หมายเลขสถานที่รับ

    ข้อกำหนดเพิ่มเติม:
    - หากข้อมูลใดหาไม่เจอ ให้ใส่ค่าเป็น `null`
    - สำหรับข้อมูลตัวเลข (item_number, Receipt Qty, Location) ให้แปลงเป็น Number Type (ไม่ต้องมี comma)
    - ผลลัพธ์ต้องเป็น JSON ที่สมบูรณ์เท่านั้น ห้ามมีข้อความอื่นปะปน
    """

    json_result_str = analyze_images_with_gemini(images, extraction_prompt)

    if json_result_str:
        try:
            # ตรวจสอบและบันทึกเป็นไฟล์ JSON
            json_data = json.loads(json_result_str)
            with open(JSON_OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=4, ensure_ascii=False)
            print(f"สร้างไฟล์ {JSON_OUTPUT_FILENAME} สำเร็จ!")
        except json.JSONDecodeError:
            print("ผลลัพธ์ที่ได้จาก Gemini ไม่ใช่ JSON ที่ถูกต้อง:")
            print(json_result_str)
    else:
        print("ไม่ได้รับผลลัพธ์จาก Gemini API")

if __name__ == "__main__":
    main()





