import logging
import os
import cv2
import numpy as np
import pytesseract
from PIL import Image
from io import BytesIO
import requests

logger = logging.getLogger(__name__)


def padded_crop(img, x0, y0, x1, y1, pad=10):
    h, w = img.shape[:2]
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(w, x1 + pad)
    y1 = min(h, y1 + pad)
    return img[y0:y1, x0:x1]


def extract_text_from_image_advanced(image_url):
    try:
        response = requests.get(image_url, timeout=10)
        image = Image.open(BytesIO(response.content)).convert("RGB")
        image_np = np.array(image)

       
        gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape

        ocr_config = r'--oem 3 --psm 6'
        full_text = pytesseract.image_to_string(gray, config=ocr_config).strip()


        top_right_crop = padded_crop(gray, 400, 5, 1000, 200, pad=10)
        _, amt_bin = cv2.threshold(top_right_crop, 170, 255, cv2.THRESH_BINARY_INV)
        top_right_text = pytesseract.image_to_string(amt_bin, config='--psm 8').strip()


        hsv = cv2.cvtColor(image_np, cv2.COLOR_RGB2HSV)
        v_channel = hsv[:, :, 2]

      
        bottom_right_crop = padded_crop(v_channel, 300, 600, 1200, 1200, pad=15)

       
        loc_bin = cv2.adaptiveThreshold(
            bottom_right_crop, 255,
            cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY_INV,
            11, 2
        )

     
        bottom_right_text = pytesseract.image_to_string(loc_bin, config='--psm 8').strip()




        try:

            template_path = os.path.join(os.path.dirname(__file__), "assets", "deadline_template.jpg")
            template = cv2.imread(template_path, 0)
            if template is None:
                raise FileNotFoundError(f"Could not load template at {template_path}")


            deadline_text = ""

            if template is not None:
                result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)

                if max_val > 0.7:
                    tx, ty = max_loc
                    th, tw = template.shape

                  
                    x0 = tx + tw + 10
                    y0 = ty
                    x1 = min(w, x0 + 1000)
                    y1 = min(h, ty + th + 40)

                    deadline_crop = gray[y0:y1, x0:x1]
                    _, deadline_bin = cv2.threshold(deadline_crop, 170, 255, cv2.THRESH_BINARY)
                    deadline_text = pytesseract.image_to_string(deadline_bin, config='--psm 7').strip()

                    
                else:
                    logger.warning("Template match for DEADLINE failed. Falling back to manual crop.")
            else:
                logger.warning("Deadline template image not found. Falling back to manual crop.")

         
            if not deadline_text:
                manual_crop = padded_crop(gray, 22, 182, 750, 400, pad=10)
                _, manual_bin = cv2.threshold(manual_crop, 170, 255, cv2.THRESH_BINARY)
                deadline_text = pytesseract.image_to_string(manual_bin, config='--psm 6').strip()

               

        except Exception as e:
            logger.warning(f"Deadline extraction failed: {e}")
            deadline_text = ""



        return {
            "full_text": full_text,
            "top_right_text": top_right_text,
            "bottom_right_text": bottom_right_text,
            "deadline_text": deadline_text
        }

    except Exception as e:
        logger.warning(f"OCR advanced failed: {e}")
        return {
            "full_text": "",
            "top_right_text": "",
            "bottom_right_text": "",
            "deadline_text": ""
        }
    

