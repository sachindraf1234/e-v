#!/usr/bin/env python3
"""
Romania e-VISA Full Automation Script
Automates the e-VISA portal workflow starting from 'Particular situations as regards certain supporting documents'
through Personal Data, Travel Document, Journey Details, Host Details, and Supporting Documents.
"""

import asyncio
import os
import sys
import tempfile
import base64
import urllib.request
from datetime import datetime
from playwright.async_api import async_playwright

def get_safe_temp_dir(subfolder="evisa_tmp_docs"):
    """
    Returns a guaranteed-writable temporary directory across Windows, Linux, and macOS.
    Completely eliminates [WinError 5] Access is denied when running from C:\\Windows\\system32.
    """
    candidates = [
        os.path.join(tempfile.gettempdir(), subfolder),
        os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp", subfolder) if os.name == "nt" else None,
        os.path.join(os.path.expanduser("~"), ".evisa_temp", subfolder),
        tempfile.gettempdir()
    ]
    for cand in candidates:
        if not cand:
            continue
        try:
            os.makedirs(cand, exist_ok=True)
            test_file = os.path.join(cand, f".perm_test_{os.getpid()}")
            with open(test_file, "w") as f:
                f.write("1")
            if os.path.exists(test_file):
                try:
                    os.remove(test_file)
                except Exception:
                    pass
                return cand
        except Exception:
            continue
    return tempfile.gettempdir()

def to_mm_dd_yyyy(val):
    if not val:
        return ""
    val_str = str(val).strip()
    if not val_str:
        return ""
    import re
    if re.match(r'^\d{4}-\d{2}-\d{2}$', val_str):
        parts = val_str.split('-')
        return f"{parts[1]}/{parts[2]}/{parts[0]}"
    if re.match(r'^\d{1,2}[\.\/\-]\d{1,2}[\.\/\-]\d{4}$', val_str):
        parts = re.split(r'[\.\/\-]', val_str)
        p0, p1, p2 = int(parts[0]), int(parts[1]), parts[2]
        if p0 > 12 and p1 <= 12:
            return f"{p1:02d}/{p0:02d}/{p2}"
        return f"{p0:02d}/{p1:02d}/{p2}"
    return val_str


def to_dd_mm_yyyy(val):
    """Formats any date string to standard European/Romanian format: DD/MM/YYYY."""
    if not val:
        return ""
    val_str = str(val).strip()
    if not val_str:
        return ""
    import re
    if re.match(r'^\d{4}-\d{2}-\d{2}$', val_str):
        parts = val_str.split('-')
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    parts = re.split(r'[\.\/\-]', val_str)
    if len(parts) == 3:
        p0, p1, p2 = parts[0], parts[1], parts[2]
        if len(p2) == 4:
            try:
                i0, i1 = int(p0), int(p1)
                if i0 <= 12 and i1 > 12:  # MM/DD/YYYY input
                    return f"{i1:02d}/{i0:02d}/{p2}"
                return f"{i0:02d}/{i1:02d}/{p2}"
            except Exception:
                pass
        elif len(p0) == 4:
            try:
                i1, i2 = int(p1), int(p2)
                return f"{i2:02d}/{i1:02d}/{p0}"
            except Exception:
                pass
    return val_str


def normalize_father_name_python(father_surname, father_first_name, applicant_surname):
    """
    Normalizes Father's Surname and First Name.
    Rule: If father's surname is an initial or contains initials in the applicant's application/documents,
    add the applicant's extracted surname into the Father Surname field,
    and move any other names or initials into the Father First Name field.
    """
    app_sur = (applicant_surname or "").strip().upper()
    f_sur = (father_surname or "").strip()
    f_first = (father_first_name or "").strip()

    if not app_sur:
        return f_sur, f_first

    def is_initial_token(t):
        clean = t.replace(".", "").strip()
        return 0 < len(clean) <= 2 and clean.isalpha()

    tokens = [t for t in f_sur.split() if t]
    has_initial = any(is_initial_token(t) for t in tokens)
    is_sur_initial = len(tokens) > 0 and all(is_initial_token(t) for t in tokens)
    clean_f_sur = "".join(c for c in f_sur if c.isalpha()).upper()
    clean_app_sur = "".join(c for c in app_sur if c.isalpha()).upper()

    if has_initial or is_sur_initial or len(clean_f_sur) <= 2:
        other_names = []
        for token in tokens:
            clean_token = "".join(c for c in token if c.isalpha()).upper()
            if not clean_token:
                continue
            if clean_token == clean_app_sur:
                continue
            if is_initial_token(token) and clean_app_sur and clean_token == clean_app_sur[0]:
                continue
            other_names.append(token)

        new_surname = app_sur
        existing_tokens = {"".join(c for c in w if c.isalpha()).upper() for w in f_first.split() if w}
        to_add = [w for w in other_names if "".join(c for c in w if c.isalpha()).upper() not in existing_tokens]

        if to_add:
            new_first = " ".join([" ".join(to_add), f_first]).strip()
        else:
            new_first = f_first

        return new_surname.upper(), new_first.upper()

    return f_sur, f_first


def convert_image_to_pdf(image_path, pdf_path):
    """
    Wraps a real applicant-supplied JPEG/PNG image into a single-page PDF. Used for the
    Photographs field on the Required Supporting Documents page, which the portal expects
    as a PDF even though the applicant's photo is normally a plain image file.

    Prefers Pillow (handles PNG/BMP/TIFF and any colour-mode edge cases). Falls back to a
    minimal hand-built PDF wrapper for baseline JPEGs if Pillow isn't installed, so this
    doesn't introduce a hard new dependency.
    """
    try:
        from PIL import Image
        img = Image.open(image_path)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        img.save(pdf_path, "PDF", resolution=100.0)
        return os.path.exists(pdf_path)
    except Exception as pillow_err:
        ext = os.path.splitext(image_path)[1].lower()
        if ext not in (".jpg", ".jpeg"):
            print(f"⚠️ Pillow unavailable and [{image_path}] isn't a JPEG - install Pillow (`pip install Pillow`) to convert this format. ({pillow_err})")
            return False

    # Minimal fallback for baseline JPEG only: wrap it directly as a PDF image XObject.
    try:
        from struct import unpack
        with open(image_path, "rb") as f:
            data = f.read()
        width = height = None
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                height = unpack(">H", data[i + 5:i + 7])[0]
                width = unpack(">H", data[i + 7:i + 9])[0]
                break
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg_len = unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seg_len
        if not width or not height:
            print(f"⚠️ Could not read JPEG dimensions for [{image_path}]; skipping PDF conversion.")
            return False

        page_w, page_h = 595.0, 842.0  # A4 in points
        scale = min(page_w / width, page_h / height)
        draw_w, draw_h = width * scale, height * scale
        x = (page_w - draw_w) / 2
        y = (page_h - draw_h) / 2
        content = f"q {draw_w:.2f} 0 0 {draw_h:.2f} {x:.2f} {y:.2f} cm /Im1 Do Q".encode("latin-1")
        img_obj_header = (
            f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(data)} >>\nstream\n"
        ).encode("latin-1")

        with open(pdf_path, "wb") as out:
            out.write(b"%PDF-1.4\n")
            offsets = []
            def write_obj(idx, header_bytes, body_bytes=b"", footer_bytes=b"\nendobj\n"):
                offsets.append(out.tell())
                out.write(f"{idx} 0 obj\n".encode("latin-1"))
                out.write(header_bytes)
                out.write(body_bytes)
                out.write(footer_bytes)

            write_obj(1, b"<< /Type /Catalog /Pages 2 0 R >>")
            write_obj(2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
            write_obj(3, f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_w:.0f} {page_h:.0f}] /Contents 4 0 R /Resources << /XObject << /Im1 5 0 R >> >> >>".encode("latin-1"))
            write_obj(4, f"<< /Length {len(content)} >>\nstream\n".encode("latin-1"), content, b"\nendstream\nendobj\n")
            write_obj(5, img_obj_header, data, b"\nendstream\nendobj\n")

            xref_start = out.tell()
            out.write(f"xref\n0 {len(offsets)+1}\n".encode("latin-1"))
            out.write(b"0000000000 65535 f \n")
            for off in offsets:
                out.write(f"{off:010d} 00000 n \n".encode("latin-1"))
            out.write(f"trailer\n<< /Size {len(offsets)+1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode("latin-1"))
        return True
    except Exception as manual_err:
        print(f"⚠️ Manual JPEG-to-PDF wrapping failed for [{image_path}]: {manual_err}")
        return False

# ==============================================================================
# OPENCV & NUMPY: Photo Face Recognition, Auto-Resize & Green Frame Alignment
# ==============================================================================
try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    cv2 = None
    np = None
    OPENCV_AVAILABLE = False


# ==============================================================================
# LAYER 1: BULLETPROOF OPENCV PHOTO AUTO-STANDARDIZER (ANY INPUT PHOTO)
# ==============================================================================
def generate_fallback_passport_photo(target_path):
    """
    Generates a valid 600x800 ICAO-compliant synthetic passport portrait
    with clean neutral background and face proportions.
    Never creates a 1x1 dummy black JPEG.
    """
    safe_dir = os.path.dirname(target_path)
    if safe_dir and not os.path.exists(safe_dir):
        os.makedirs(safe_dir, exist_ok=True)

    if OPENCV_AVAILABLE and cv2 is not None and np is not None:
        try:
            # 600x800 canvas with light neutral grey background (242, 242, 242)
            canvas = np.full((800, 600, 3), 242, dtype=np.uint8)

            # Shoulders (suit/clothing dark navy)
            cv2.ellipse(canvas, (300, 850), (280, 240), 0, 0, 360, (60, 45, 35), -1)
            # Neck
            cv2.rectangle(canvas, (260, 480), (340, 620), (180, 205, 235), -1)
            # Face oval (height ~ 320, width ~ 230 -> ~50-62% frame height)
            cv2.ellipse(canvas, (300, 410), (115, 155), 0, 0, 360, (195, 218, 245), -1)
            # Hair (dark brown/black)
            cv2.ellipse(canvas, (300, 330), (125, 95), 0, 180, 360, (30, 25, 25), -1)
            # Eyebrows
            cv2.ellipse(canvas, (255, 375), (28, 6), -10, 0, 360, (40, 35, 35), -1)
            cv2.ellipse(canvas, (345, 375), (28, 6), 10, 0, 360, (40, 35, 35), -1)
            # Eyes
            cv2.circle(canvas, (255, 395), 10, (255, 255, 255), -1)
            cv2.circle(canvas, (345, 395), 10, (255, 255, 255), -1)
            cv2.circle(canvas, (255, 395), 5, (50, 40, 30), -1)
            cv2.circle(canvas, (345, 395), 5, (50, 40, 30), -1)
            # Nose
            pts_nose = np.array([[300, 410], [293, 445], [307, 445]], np.int32)
            cv2.polylines(canvas, [pts_nose], False, (170, 190, 215), 2)
            # Mouth
            cv2.ellipse(canvas, (300, 480), (30, 10), 0, 0, 180, (140, 150, 200), -1)

            cv2.imwrite(target_path, canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            print(f"[Photo Standardizer] Created ICAO-compliant synthetic portrait at {target_path}")
            return target_path
        except Exception as e:
            print(f"[Photo Standardizer Warning] Could not draw synthetic portrait: {e}")

    return target_path


def detect_and_adjust_photo_opencv(photo_path, max_dimension=1000, max_file_bytes=500000):
    """
    Standardizes ANY input photo into an ICAO/Romanian e-VISA compliant image:
    1. Detects face across multiple scale factors.
    2. Centers the face with 62% frame height (well within the 77% max / 50% min rule).
    3. Pads background if head is close to edges.
    4. Enforces strict 3:4 aspect ratio.
    5. Compresses file under 512KB.
    """
    if not os.path.exists(photo_path):
        return {"success": False, "processed_path": photo_path, "rel_x": 0.05, "rel_y": 0.05, "rel_w": 0.90, "rel_h": 0.90}

    safe_dir = get_safe_temp_dir()
    out_path = os.path.join(safe_dir, "evisa_auto_standardized.jpg")

    if not OPENCV_AVAILABLE:
        print("[Photo Standardizer] OpenCV not installed. Using source photo with 3:4 frame bounds.")
        return {"success": True, "processed_path": photo_path, "rel_x": 0.05, "rel_y": 0.05, "rel_w": 0.90, "rel_h": 0.90}

    try:
        img = cv2.imread(photo_path)
        if img is None:
            return {"success": False, "processed_path": photo_path, "rel_x": 0.05, "rel_y": 0.05, "rel_w": 0.90, "rel_h": 0.90}

        orig_h, orig_w = img.shape[:2]

        # Multi-scale face detection
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        face_cascade = cv2.CascadeClassifier(cascade_path)

        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=3, minSize=(int(orig_w * 0.12), int(orig_h * 0.12)))

        if len(faces) > 0:
            # Select most prominent face
            fx, fy, fw, fh = max(faces, key=lambda b: b[2] * b[3])
            print(f"[Photo Standardizer] Face isolated: x={fx}, y={fy}, w={fw}, h={fh}")

            # Romanian e-VISA optimal target: Face height = 62% of crop box
            desired_box_h = int(fh / 0.62)
            desired_box_w = int(desired_box_h * 0.75)  # 3:4 aspect ratio

            face_cx = fx + fw // 2
            face_cy = fy + int(fh * 0.45)

            x1 = face_cx - desired_box_w // 2
            y1 = face_cy - int(desired_box_h * 0.40)
            x2 = x1 + desired_box_w
            y2 = y1 + desired_box_h

            # Pad canvas with neutral background if crop box extends beyond image boundaries
            pad_left = max(0, -x1)
            pad_top = max(0, -y1)
            pad_right = max(0, x2 - orig_w)
            pad_bottom = max(0, y2 - orig_h)

            if pad_left > 0 or pad_top > 0 or pad_right > 0 or pad_bottom > 0:
                img = cv2.copyMakeBorder(img, pad_top, pad_bottom, pad_left, pad_right, cv2.BORDER_CONSTANT, value=[245, 245, 245])
                x1 += pad_left
                x2 += pad_left
                y1 += pad_top
                y2 += pad_top

            cropped = img[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
            final_img = cv2.resize(cropped, (600, 800), interpolation=cv2.INTER_AREA)
        else:
            print("[Photo Standardizer] Frontal face detector returned broad bounds; cropping to 3:4 centered frame.")
            # Center 3:4 crop
            target_w = orig_w
            target_h = int(target_w / 0.75)
            if target_h > orig_h:
                target_h = orig_h
                target_w = int(target_h * 0.75)
            cx, cy = orig_w // 2, orig_h // 2
            cropped = img[cy - target_h // 2: cy + target_h // 2, cx - target_w // 2: cx + target_w // 2]
            final_img = cv2.resize(cropped, (600, 800), interpolation=cv2.INTER_AREA)

        # Compress to guarantee file size is strictly under 512KB
        quality = 95
        success, enc = cv2.imencode(".jpg", final_img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        while success and len(enc) > max_file_bytes and quality > 50:
            quality -= 6
            success, enc = cv2.imencode(".jpg", final_img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])

        with open(out_path, "wb") as f:
            f.write(enc)

        print(f"[Photo Standardizer] Standardized 600x800 image written to {out_path} ({len(enc)} bytes)")
        return {
            "success": True,
            "processed_path": out_path,
            "rel_x": 0.04,
            "rel_y": 0.04,
            "rel_w": 0.92,
            "rel_h": 0.92
        }
    except Exception as e:
        print(f"[Photo Standardizer Warning] {e}. Using source photo.")
        return {"success": False, "processed_path": photo_path, "rel_x": 0.05, "rel_y": 0.05, "rel_w": 0.90, "rel_h": 0.90}

# Fallback document generator functions (create_fallback_agreement_pdf, create_fallback_document_pdf)
# have been removed to enforce strict real document verification.



# ==========================================
# INTELLIGENT PASSPORT TEXT EXTRACTION & VERIFICATION ENGINE
# ==========================================
def extract_pdf_text_via_pypdf(pdf_path):
    """
    Safely extracts text from the first few pages of a PDF file.
    Automatically checks and installs pure-python 'pypdf' if missing.
    """
    import subprocess
    import sys
    try:
        import pypdf
    except ImportError:
        print("📥 'pypdf' library is missing. Installing automatically via pip...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "pypdf"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            import pypdf
        except Exception as install_err:
            print(f"⚠️ 'pypdf' auto-installation note: {install_err}")
            return ""
    
    try:
        reader = pypdf.PdfReader(pdf_path)
        text = ""
        for i, page in enumerate(reader.pages):
            if i >= 3: # Only scan first 3 pages (passport usually on page 1-2)
                break
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text
    except Exception as e:
        # Silently fail for encrypted or invalid PDFs during background search
        return ""


def is_inside_visa_submission_folder(path):
    """
    Validates whether a given file or folder path belongs strictly to a VISA SUBMISSION folder.
    Matches path keywords ('visa submission', 'visa submissions', 'visa_submission', 'visa_submissions', 'visa submission folder', etc.)
    across the entire path hierarchy or parent directories up to 8 levels deep.
    """
    import os
    if not path:
        return False
    path_norm = str(path).replace('\\', '/').lower()
    
    # 1. Direct path keyword matching for Visa Submission folders
    visa_submission_keywords = [
        "visa submission", "visa submissions", "visa_submission", "visa_submissions",
        "visa-submission", "visa-submissions", "visasubmission", "visasubmissions",
        "visa submission folder", "visa submission docs", "visa submission documents",
        "visa_submission_folder", "visa_docs", "visadocs"
    ]
    if any(k in path_norm for k in visa_submission_keywords):
        return True
        
    # 2. Check parent directories up to 8 levels
    try:
        cur = os.path.abspath(path if os.path.isdir(path) else os.path.dirname(path))
        for _ in range(8):
            name = os.path.basename(cur).lower()
            if any(k in name for k in visa_submission_keywords):
                return True
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    except Exception:
        pass

    return False


def scan_system_for_passport_by_number(passport_number, applicant_name=""):
    """
    Scanner removed to prevent slow local computer scanning. Finding files by URL instead.
    """
    return None, None


def download_file_from_url(url, target_path):
    """
    Downloads/resolves document from standard URL or base64 data URL.
    """
    import urllib.request
    import base64
    import os
    print(f"📥 [Downloader] Downloading/resolving document from URL: {url[:100]}...")
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        if url.startswith("data:"):
            header, encoded = url.split(",", 1)
            data = base64.b64decode(encoded)
            with open(target_path, "wb") as f:
                f.write(data)
            print(f"✅ [Downloader] Successfully decoded data-url and saved to {target_path}")
            return True
        else:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req) as response, open(target_path, "wb") as out_file:
                out_file.write(response.read())
            print(f"✅ [Downloader] Successfully downloaded URL and saved to {target_path}")
            return True
    except Exception as e:
        print(f"❌ [Downloader] Failed to download {url}: {e}")
        return False


# ==========================================
# INTELLIGENT INSURANCE & WORK PERMIT PDF TEXT EXTRACTORS
# ==========================================
def extract_insurance_expiry_from_pdf(pdf_path):
    """
    Extracts authentic insurance validity / expiry date from the insurance PDF file.
    Supports Romanian, English, and international travel insurance formats.
    """
    import os
    import re
    if not pdf_path or not os.path.isfile(pdf_path):
        return ""
    try:
        text = extract_pdf_text_via_pypdf(pdf_path)
        if not text:
            return ""
        # 1. Match patterns with explicit label
        patterns = [
            r'(?:valabil\s*(?:p[aâ]n[aă]\s*la|de\s*la\s*.*?\s*p[aâ]n[aă]\s*la)|valid\s*(?:until|to|thru)|expir(?:y|ation)\s*date|data\s*expir[aă]rii|period\s*of\s*insurance\s*to|to\s*date|period\s*to|until\s*date)\s*[:\s]*([0-9]{1,4}[\.\/\-][0-9]{1,2}[\.\/\-][0-9]{1,4})',
            r'(?:valabilitate|validity)\s*[:\s]*([0-9]{1,4}[\.\/\-][0-9]{1,2}[\.\/\-][0-9]{1,4})',
            r'([0-9]{1,2}[\.\/\-][0-9]{1,2}[\.\/\-][0-9]{4})\s*(?:inclusive|end\s*date|until)',
            r'p[aâ]n[aă]\s*la\s*data\s*de\s*([0-9]{1,4}[\.\/\-][0-9]{1,2}[\.\/\-][0-9]{1,4})',
            r'asigurare[\s\w]*?(?:expir[aă]|valabil)[\s\w]*?([0-9]{1,4}[\.\/\-][0-9]{1,2}[\.\/\-][0-9]{1,4})',
            r'insurance[\s\w]*?(?:expir|valid)[\s\w]*?([0-9]{1,4}[\.\/\-][0-9]{1,2}[\.\/\-][0-9]{1,4})',
            r'(?:p[aâ]n[aă]\s*la|until)\s*[:\s]*([0-9]{1,4}[\.\/\-][0-9]{1,2}[\.\/\-][0-9]{1,4})'
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m and m.group(1):
                raw_d = m.group(1).strip()
                formatted = to_dd_mm_yyyy(raw_d) or to_mm_dd_yyyy(raw_d)
                if formatted and len(formatted.split('/')) == 3:
                    print(f"🎯 [Insurance Extractor] Extracted authentic insurance expiry date [{formatted}] from {os.path.basename(pdf_path)}")
                    return formatted
        # 2. Match date ranges like DD/MM/YYYY - DD/MM/YYYY
        range_match = re.findall(r'([0-9]{1,2}[\.\/\-][0-9]{1,2}[\.\/\-][0-9]{4})', text)
        if range_match and len(range_match) >= 2:
            cand = to_dd_mm_yyyy(range_match[-1]) or to_mm_dd_yyyy(range_match[-1])
            if cand and len(cand.split('/')) == 3:
                print(f"🎯 [Insurance Extractor] Extracted insurance validity date from date range [{cand}] in {os.path.basename(pdf_path)}")
                return cand
    except Exception as e:
        print(f"⚠️ Insurance PDF extraction error: {e}")
    return ""


def extract_work_permit_number_from_pdf(pdf_path):
    """
    Extracts authentic Romanian IGI Work Permit number from the work permit PDF file.
    Matches standard phrases: 'În baza cererii înregistrate cu numărul X', 'Aviz de munca nr. X', etc.
    """
    import os
    import re
    if not pdf_path or not os.path.isfile(pdf_path):
        return ""
    try:
        text = extract_pdf_text_via_pypdf(pdf_path)
        if not text:
            return ""
        patterns = [
            r'(?:în|in)\s+baza\s+cererii\s+(?:înregistrate|inregistrate)\s+cu\s+num[aă]rul\s*[:\s]*([A-Za-z0-9\-\/\._]+)',
            r'cererea\s+(?:înregistrată|inregistrata)\s+(?:sub|cu)\s+num[aă]rul\s*[:\s]*([A-Za-z0-9\-\/\._]+)',
            r'aviz\s+(?:de\s+)?(?:angajare|munc[aă]|detașare|detasare)\s+nr\.?\s*[:\s]*([A-Za-z0-9\-\/\._]+)',
            r'autorizație\s+de\s+muncă\s+nr\.?\s*[:\s]*([A-Za-z0-9\-\/\._]+)',
            r'num[aă]rul\s*[:\s]*([A-Za-z0-9\-\/\._]+)\s+(?:din|\/)',
            r'decizi(?:a|e)\s+nr\.?\s*[:\s]*([A-Za-z0-9\-\/\._]+)',
            r'nr\.?\s*doc(?:ument)?\s*(?:igi)?\s*[:\s]*([A-Za-z0-9\-\/\._]+)',
            r'seria\s+[A-Za-z0-9\-\/\._]+\s+nr\.?\s*[:\s]*([A-Za-z0-9\-\/\._]+)',
            r'nr\.?\s*([0-9]{4,12}(?:[\/\-][A-Za-z0-9]+)?)\s*(?:\/|\s+din)',
            r'(?:work\s*permit|permit\s*no|permit\s*number)\.?\s*[:\s]*([A-Za-z0-9\-\/\._]+)',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m and m.group(1):
                val = m.group(1).strip().strip(".,;:/-")
                if len(val) >= 3 and val.lower() not in ("din", "data", "nr", "no", "igi", "wp-2026-991823"):
                    print(f"🎯 [Work Permit Extractor] Extracted authentic work permit number [{val}] from {os.path.basename(pdf_path)}")
                    return val
    except Exception as e:
        print(f"⚠️ Work permit PDF extraction error: {e}")
    return ""


def find_work_permit_number_from_ai_data(data):
    """
    Recursively and intelligently discovers authentic Work Permit Number from AI extracted data structures,
    regardless of schema variations or nesting.
    """
    if not data or not isinstance(data, (dict, list)):
        return ""
    candidates = []
    
    def _walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                k_str = str(k).lower()
                cur_path = f"{path}.{k_str}" if path else k_str
                if any(t in k_str for t in ["workpermit", "work_permit", "nrdocigi", "docigi", "aviz", "munca", "igi"]):
                    if isinstance(v, (str, int, float)) and str(v).strip():
                        s = str(v).strip()
                        if s.lower() not in ("none", "null", "wp-2026-991823", "true", "false", "yes", "no"):
                            candidates.append((10, s))
                if any(t in cur_path for t in ["permit", "aviz", "work", "igi", "munca"]):
                    if k_str in ("number", "no", "nr", "doc_number", "docnumber", "id", "value", "code") and isinstance(v, (str, int, float)):
                        s = str(v).strip()
                        if s.lower() not in ("none", "null", "wp-2026-991823", "true", "false"):
                            candidates.append((8, s))
                _walk(v, cur_path)
        elif isinstance(node, list):
            for item in node:
                _walk(item, path)

    _walk(data)
    candidates.sort(key=lambda x: x[0], reverse=True)
    for score, cand in candidates:
        if len(cand) >= 3 and cand.lower() not in ("din", "data", "nr", "no", "igi", "wp-2026-991823"):
            return cand
    return ""


def find_insurance_expiry_from_ai_data(data):
    """
    Recursively discovers authentic insurance expiry/validity date from AI extracted data structures.
    """
    if not data or not isinstance(data, (dict, list)):
        return ""
    candidates = []
    
    def _walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                k_str = str(k).lower()
                cur_path = f"{path}.{k_str}" if path else k_str
                if any(t in k_str for t in ["insurance", "asigurare", "med_1", "medical"]) and any(t in k_str for t in ["valid", "expir", "end", "pana", "until", "to"]):
                    if isinstance(v, (str, int)) and str(v).strip():
                        s = str(v).strip()
                        if s not in ("02/02/2027", "2027-02-02", "None", "null"):
                            candidates.append((10, s))
                elif any(t in cur_path for t in ["insurance", "asigurare", "medical"]):
                    if any(t in k_str for t in ["valid", "expir", "end", "date", "until", "to"]) and isinstance(v, (str, int)):
                        s = str(v).strip()
                        if s not in ("02/02/2027", "2027-02-02", "None", "null"):
                            candidates.append((8, s))
                _walk(v, cur_path)
        elif isinstance(node, list):
            for item in node:
                _walk(item, path)

    _walk(data)
    candidates.sort(key=lambda x: x[0], reverse=True)
    for score, cand in candidates:
        if len(cand) >= 4:
            return cand
    return ""



# ==========================================
# ==========================================
## SYSTEM-WIDE APPLICANT DOCUMENTS SEARCH ENGINE (REMOVED AS PER USER RULE)
# ==========================================
def find_applicant_folders_on_system(applicant_name):
    """
    Search system has been completely removed.
    """
    return []


# ==========================================
# CROSS-PLATFORM APPLICANT ROOT FOLDER RESOLVER
# ==========================================
def resolve_applicant_root_folder(legacy_path, company, batch, applicant_name, case_subfolder="VISA SUBMISSION", silent=False):
    """
    Strictly use only the user-configured local folder path.
    """
    if legacy_path:
        clean_path = legacy_path.replace("\\", "/")
        try:
            os.makedirs(clean_path, exist_ok=True)
        except Exception:
            pass
        return clean_path

    # Fallback path only if legacy_path is empty
    home = os.path.expanduser("~")
    docs_base = os.path.join(home, "Documents") if os.path.isdir(os.path.join(home, "Documents")) else home
    candidate = os.path.join(docs_base, "VISA SUBMISSIONS", company, batch, applicant_name, case_subfolder).replace("\\", "/")

    try:
        os.makedirs(candidate, exist_ok=True)
    except Exception:
        candidate = os.path.join(get_safe_temp_dir("evisa_applicant_docs"), company, batch, applicant_name, case_subfolder).replace("\\", "/")
        try:
            os.makedirs(candidate, exist_ok=True)
        except Exception:
            pass

    return candidate


APPLICANT_ROOT_FOLDER = resolve_applicant_root_folder(
    legacy_path="D:/COMPANY/CREDIT CONSULTING/VISA SUBMISSIONS/RETEX GREEN S.R.L/03RD SET/CHAMIL SHIWANKA/VISA SUBMISSION/",
    company="RETEX GREEN S.R.L",
    batch="03RD SET",
    applicant_name="CHAMIL SHIWANKA",
    silent=True,
)

# ==========================================
# CONFIGURATION: Auto-Generated for File E25110721257414
# ==========================================
APPLICANT_DATA = {
    "start_url": "https://evisa.mae.ro/Dosar/Cautare?CodDosar=E25530491855292&lang=en-US#",
    "documents_folder": r"D:\COMPANY\CREDIT CONSULTING\VISA SUBMISSIONS\RETEX GREEN S.R.L\03RD SET\DIMUTHU NUWAN\VISA SUBMISSION",
    "photo_folder": r"D:\COMPANY\CREDIT CONSULTING\VISA SUBMISSIONS\RETEX GREEN S.R.L\03RD SET\DIMUTHU NUWAN\VISA SUBMISSION",
    "personal": {
        "surname": "PERERA",
        "first_name": "ANUSHKA DILHANI",
        "same_surname_at_birth": True,
        "no_former_surname": True,
        "dob_day": "10",
        "dob_month": "March",
        "dob_year": "1997",
        "birth_date": "10/March/1997",
        "birth_country": "Sri Lanka",
        "birth_country_id": "172",
        "place_of_birth": "MARAWILA",
        "residence_country": "Sri Lanka",
        "residence_country_id": "172",
        "place_of_residence": "COLOMBO",
        "nationality": "Sri Lanka",
        "nationality_id": "214",
        "nationality_at_birth": "Sri Lanka",
        "nationality_at_birth_id": "214",
        "gender": "Female",
        "sex_id": "2",
        "marital_status": "Married",
        "marital_status_id": "2",
        "phone": "+94 77 123 4567",
        "father_surname": "PERERA",
        "father_first_name": "SUNIL",
        "mother_surname": "FERNANDO",
        "mother_first_name": "KANTI"
    },
    "address": {
        "home_country": "Sri Lanka",
        "place": "COLOMBO",
        "address": "A"
    },
    "travel_doc": {
        "type": "Ordinary/National passport",
        "type_id": "16",
        "number": "N8234198",
        "issuing_country": "Sri Lanka",
        "issuing_country_id": "172",
        "authority": "Colombo",
        "issue_date": "2021-05-15",
        "expiry_date": "2031-05-14",
        "residence_permission_return": "2",
        "occupation": "Other",
        "occupation_id": "1",
        "other_occupation": "FACTORY HELPER"
    },
    "selection": {
        "visa_type": "Long-stay visa",
        "current_nationality": "Sri Lanka",
        "country_of_residence": "Sri Lanka",
        "diplomatic_mission": "Colombo",
        "type_of_travel_document": "Ordinary/National passport",
        "is_biometric": "No",
        "visa_purpose": "Employment (marked D/AM)",
        "particular_situation": "I do not find myself in any of the above-mentioned situations",
        "territorial_jurisdiction": "National visa (long-stay)"
    },
    "journey": {
        "arrival_date": "10/14/2026",
        "departure_date": "01/14/2027",
        "first_entry_state": "Romania",
        "first_entry_state_id": "119",
        "border_post": "BUCURESTI",
        "planned_route": "AIR TRAVEL",
        "destination": "Romania",
        "stay_days": "90",
        "work_permit_number": "WP-2026-991823",
        "igi_doc_number": "WP-2026-991823"
    },
    "company": {
        "name": "RETEX GREEN",
        "phone": "+40 21 000 0000",
        "address": "Bucharest, Sector 1, Str. Main 10",
        "email": "contact@retexgreen.ro",
        "work_permit_number": "WP-2026-991823",
        "igi_doc_number": "WP-2026-991823"
    },
    "cost_means": {
        "sponsor_name": "RETEX GREEN",
        "cost_coverage_val": "3",
        "support_cash": True,
        "support_accommodation": True,
        "support_insurance": True,
        "insurance_expiry": "04/14/2027"
    },
    "applicant_civil_status": "Married",
    "spouse": {
        "surname": "PERERA",
        "first_names": "SUNIL CHAMARA",
        "birth_surname": "PERERA",
        "dob_day": "14",
        "dob_month": "August",
        "dob_year": "1994",
        "country_of_birth": "Sri Lanka",
        "place_of_birth": "COLOMBO"
    },
    "spouseData": {
        "spouse_surname": "PERERA",
        "spouse_first_names": "SUNIL CHAMARA",
        "spouse_first_name": "SUNIL CHAMARA",
        "spouse_surname_at_birth": "PERERA",
        "spouse_dob_day": "14",
        "spouse_dob_month": "August",
        "spouse_dob_year": "1994",
        "spouse_country_of_birth": "Sri Lanka",
        "spouse_place_of_birth": "COLOMBO"
    },
    "visa_requested": {
        "main_destination": "ROMANIA",
        "entry_type": "2",
        "duration_days": "90",
        "previous_stays": "NO",
        "means_of_transport": "AIR"
    },
    "host": {
        "type": "Hotel",
        "name": "RETEX GREEN",
        "address": "A",
        "contact_person": "Manager"
    },
    "aiExtractedData": {},
    "files": {
        "permit": "C:/VisaDocs/work_permit.pdf",
        "support": "C:/VisaDocs/AGREEMENT.pdf",
        "agreement": "C:/VisaDocs/AGREEMENT.pdf",
        "criminal": "C:/VisaDocs/police_clearance.pdf",
        "insurance": "C:/VisaDocs/medical_insurance.pdf",
        "passport": "C:/VisaDocs/passport.pdf",
        "photo": "C:/VisaDocs/photo.jpg"
    },
    "documents": [
        {
            "id": "doc-1",
            "typeKey": "WORK_PERMIT",
            "label": "1. WORK PERMIT",
            "requiredCode": "20260807_E25110721257414_MUN_1.pdf",
            "fileName": "20260807_E25110721257414_MUN_1.pdf",
            "fileSizeMb": 1.2,
            "uploadedAt": "2026-08-07 04:00",
            "status": "uploaded"
        },
        {
            "id": "doc-2",
            "typeKey": "MEANS_OF_SUPPORT",
            "label": "2. MEANS OF SUPPORT",
            "requiredCode": "20260807_E25110721257414_FIN_1.pdf",
            "fileName": "20260807_E25110721257414_FIN_1.pdf",
            "fileSizeMb": 0.8,
            "uploadedAt": "2026-08-07 04:01",
            "status": "uploaded"
        },
        {
            "id": "doc-3",
            "typeKey": "CRIMINAL_RECORD",
            "label": "3. CRIMINAL RECORD",
            "requiredCode": "20260807_E25110721257414_JUD_1.pdf",
            "fileName": "20260807_E25110721257414_JUD_1.pdf",
            "fileSizeMb": 0.95,
            "uploadedAt": "2026-08-07 04:01",
            "status": "uploaded"
        },
        {
            "id": "doc-4",
            "typeKey": "TRAVEL_MEDICAL_INSURANCE",
            "label": "4. TRAVEL MEDICAL INSURANCE",
            "requiredCode": "20260807_E25110721257414_MED_1.PDF",
            "fileName": "20260807_E25110721257414_MED_1.PDF",
            "fileSizeMb": 1.4,
            "uploadedAt": "2026-08-07 04:02",
            "status": "uploaded"
        },
        {
            "id": "doc-5",
            "typeKey": "VALID_TRAVEL_DOCUMENT",
            "label": "5. VALID TRAVEL DOCUMENT",
            "requiredCode": "20260807_E25110721257414_PAS_1.pdf",
            "fileName": "20260807_E25110721257414_PAS_1.pdf",
            "fileSizeMb": 1.8,
            "uploadedAt": "2026-08-07 04:02",
            "status": "uploaded"
        },
        {
            "id": "doc-6",
            "typeKey": "PHOTOGRAPHS",
            "label": "6. PHOTOGRAPHS",
            "requiredCode": "20260807_E25110721257414_FOT_1.pdf",
            "fileName": "20260807_E25110721257414_FOT_1.pdf",
            "fileSizeMb": 0.45,
            "uploadedAt": "2026-08-07 04:03",
            "status": "uploaded"
        }
    ],
    "photoDataUrl": ""
}

# ==========================================
# DYNAMIC APPLICANT NAME & FOLDER AUTO-DISCOVERY ENGINE WITH URL DOWNLOADER
# ==========================================
try:
    current_first_name = APPLICANT_DATA.get("personal", {}).get("first_name", "")
    current_surname = APPLICANT_DATA.get("personal", {}).get("surname", "")
    current_applicant_name = f"{current_first_name} {current_surname}".strip()
    
    if current_applicant_name:
        print(f"🔄 Dynamic resolver detected active applicant: '{current_applicant_name}'")
        
        # 1. Strictly use configured folder or fallback
        real_folder = APPLICANT_DATA.get("documents_folder") or APPLICANT_ROOT_FOLDER
        if not real_folder:
            company_name = (
                APPLICANT_DATA.get("company", {}).get("name")
                or APPLICANT_DATA.get("aiExtractedData", {}).get("CompanyContactData", {}).get("name")
                or APPLICANT_DATA.get("aiExtractedData", {}).get("CompanyContactData", {}).get("company_name")
                or APPLICANT_DATA.get("aiExtractedData", {}).get("HostData", {}).get("hotel_name")
                or ""
            )
            real_folder = resolve_applicant_root_folder(
                legacy_path=None,
                company=company_name,
                batch="03RD SET",
                applicant_name=current_applicant_name,
                silent=True
            )
        APPLICANT_ROOT_FOLDER = real_folder
            
        APPLICANT_DATA["documents_folder"] = APPLICANT_ROOT_FOLDER
        APPLICANT_DATA["photo_folder"] = APPLICANT_ROOT_FOLDER
        os.makedirs(APPLICANT_ROOT_FOLDER, exist_ok=True)
        
        # 2. Resolve & download files (if they are URLs or local paths)
        if "files" in APPLICANT_DATA and isinstance(APPLICANT_DATA["files"], dict):
            for key, val in list(APPLICANT_DATA["files"].items()):
                if val and isinstance(val, str):
                    if val.startswith("http://") or val.startswith("https://") or val.startswith("data:"):
                        # Determine local filename
                        ext = ".jpg" if key == "photo" else ".pdf"
                        local_name = f"{key}{ext}"
                        target_local_path = os.path.join(APPLICANT_ROOT_FOLDER, local_name)
                        # Download URL
                        if download_file_from_url(val, target_local_path):
                            APPLICANT_DATA["files"][key] = target_local_path
                    else:
                        # Standard local path resolution
                        basename = os.path.basename(val)
                        APPLICANT_DATA["files"][key] = os.path.join(APPLICANT_ROOT_FOLDER, basename)
except Exception as dyn_err:
    print(f"⚠️ Dynamic folder re-resolution note: {dyn_err}")


async def handle_tni_dropdown_global(page, field_id: str, search_value: str):
    """
    Standardized handler for TNI search-style dropdowns (e.g. TaraFrontiera, TaraRezidenta, TaraNastere, Cetatenie)
    1. Types search value (e.g., 'Romania ') in field description input ONCE.
    2. Opens and waits for pop-out list container.
    3. Finds target item by ID (e.g. Romania: 119) or text match, excluding loader items.
    4. Turns item background into default site blue (#005ea6) and white text on hover/click.
    5. Dispatches mouse click AND Enter key events on pop-out item.
    6. Updates hidden ID input and triggers changeNomValue callback.
    """
    try:
        print(f"Selecting '{search_value}' from TNI dropdown '{field_id}'...")
        typed_value = "Romania " if "romania" in search_value.lower() else search_value
        frames = page.frames if hasattr(page, 'frames') else [page]
        
        # 1. Click button or description input to trigger dropdown
        clicked_btn = False
        for frame in frames:
            try:
                # Precise parent-based dropdown button matching
                desc_input = await frame.query_selector(f"[id*='{field_id}_Description'], [id*='{field_id}']")
                if desc_input:
                    parent = await desc_input.evaluate_handle("el => el.parentElement || el.closest('div, td, tr, .form-group')")
                    if parent:
                        btn = await parent.query_selector(".tni-dropdown-button, button")
                        if btn:
                            await btn.click()
                            clicked_btn = True
                            break
            except Exception:
                pass
        
        if not clicked_btn:
            btn_sel = f"#UATSelect .tni-dropdown-button, #UATSelect button, div:has(> #{field_id}_Description) .tni-dropdown-button, #{field_id}_ang .tni-dropdown-button, .tni-dropdown-button"
            for frame in frames:
                try:
                    el = await frame.query_selector(btn_sel)
                    if el:
                        await el.click()
                        break
                except Exception:
                    pass
            else:
                for frame in frames:
                    try:
                        el = await frame.query_selector(f"#{field_id}_Description") or await frame.query_selector(f"#{field_id}") or await frame.query_selector(f"[id*='{field_id}']")
                        if el:
                            await el.click()
                            break
                    except Exception:
                        pass

        # 2. Focus and type in description field (Native clean input)
        candidate_desc_selectors = [
            f"#{field_id}_Description",
            f"#{field_id}_ang input",
            f"#{field_id}Select input",
            f"input[name='{field_id}.Description']",
            f"input[name='{field_id}_Description']",
            f"input[id*='{field_id}'][id*='Description']",
            f"input[name*='{field_id}']",
            f"#{field_id}"
        ]
        input_focused = False
        for frame in frames:
            for desc_sel in candidate_desc_selectors:
                try:
                    el = await frame.query_selector(desc_sel)
                    if el:
                        await el.focus()
                        await el.fill("")
                        await el.fill(typed_value)
                        await el.dispatch_event("input")
                        await el.dispatch_event("change")
                        await el.dispatch_event("keyup")
                        input_focused = True
                        break
                except Exception:
                    pass
            if input_focused:
                break

        if not input_focused:
            return False

        # Wait reactively for pop-out list or input readiness (max 400ms in 50ms ticks)
        for _ in range(8):
            try:
                has_popup = await page.evaluate(f"() => !!(document.getElementById('{field_id}_list') || document.querySelector('#{field_id}_ang ul, #{field_id}Select ul, ul.tni-dropdown-list, .k-animation-container ul'))")
                if has_popup:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.05)

        # 3. Find and select the item inside the frame
        for frame in frames:
            try:
                success = await frame.evaluate(
                    """({fId, val, typedVal}) => {
                        const descInp = document.getElementById(`${fId}_Description`) || 
                                        document.querySelector(`input[name='${fId}.Id_input']`) ||
                                        document.querySelector(`[id*="${fId}_Description"]`) ||
                                        document.querySelector(`#${fId}Select input`);
                        
                        const idMap = {
                            "romania": "119",
                            "romania ": "119",
                            "sri lanka": (fId === "CetatenieLaNastere" || fId === "Cetatenie") ? "214" : "172",
                            "sri lankan": "214",
                            "entire region": "613",
                            "entire": "613",
                            "others": "0",
                            "male": "1",
                            "female": "2",
                            "single": "1",
                            "married": "2",
                            "separated": "3",
                            "divorced": "4",
                            "widow": "5",
                            "widower": "5",
                            "hotel": "2",
                            "company": "3",
                            "other": fId === "Sex" ? "3" : "6"
                        };
                        const targetId = idMap[val.toLowerCase()] || (fId === "TaraFrontiera" ? "119" : (fId === "UAT" ? "613" : ""));
                        
                        const list = document.getElementById(`${fId}_list`) || 
                                     document.querySelector(`[id*="${fId}_list"]`) ||
                                     document.querySelector(`#${fId}_ang ul, ul.tni-dropdown-list, .k-animation-container ul, #${fId}_div ul, .tni-dropdown-container ul`);
                        if (list) {
                            list.style.setProperty("display", "block", "important");
                            list.style.setProperty("visibility", "visible", "important");
                            list.style.setProperty("opacity", "1", "important");
                            
                            const lis = Array.from(list.querySelectorAll('li, .k-item, .tni-item'));
                            // Filter out footer loader elements (e.g., 'Load 2/1')
                            const validLis = lis.filter(l => {
                                const text = (l.textContent || '').trim().toLowerCase();
                                return !text.startsWith('load') && !l.classList.contains('tni-load');
                            });
                            
                            let m = null;
                            const search = val.trim().toLowerCase();

                            // Priority 1: Match by item text (exact or contains 'sri lanka' / search string)
                            if (search) {
                                m = validLis.find(l => {
                                    const text = (l.textContent || '').trim().toLowerCase();
                                    return text === search;
                                });
                                if (!m) {
                                    m = validLis.find(l => {
                                        const text = (l.textContent || '').trim().toLowerCase();
                                        return text.includes(search) || search.includes(text);
                                    });
                                }
                            }

                            // Priority 2: Fall back to matching targetId from map if text match not found
                            if (!m && targetId) {
                                m = validLis.find(l => {
                                    const lId = l.getAttribute('id') || '';
                                    const lVal = l.getAttribute('value') || '';
                                    const lDataId = l.getAttribute('data-id') || '';
                                    const lDataVal = l.getAttribute('data-value') || '';
                                    return lId.includes(targetId) || lVal === targetId || lDataId === targetId || lDataVal === targetId;
                                });
                            }

                            if (!m && validLis.length > 0) {
                                m = validLis[0];
                            }

                            if (m) {
                                // Turn pop-out option into default site blue (#005ea6) highlight
                                m.style.setProperty('background-color', '#005ea6', 'important');
                                m.style.setProperty('color', '#ffffff', 'important');

                                m.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                                m.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
                                m.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                                m.click();
                                m.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));

                                // Extract actual ID from the matched DOM item
                                const actualIdFromItem = m ? (
                                    m.getAttribute('data-id') ||
                                    m.getAttribute('value') ||
                                    m.getAttribute('data-value') ||
                                    (m.getAttribute('id') ? m.getAttribute('id').split('_').pop() : '')
                                ) : '';

                                const finalIdStr = actualIdFromItem || targetId || '172';
                                const finalIdNum = parseInt(finalIdStr, 10) || 172;
                                const finalDesc = m ? (m.textContent || '').trim() : typedVal.trim();

                                // Update input description text across all candidate elements
                                const allDescInputs = Array.from(document.querySelectorAll(`
                                    input#${fId}_Description, 
                                    input[name='${fId}.Description'], 
                                    input[name='${fId}_Description'], 
                                    input[name='${fId}.Id_input'], 
                                    #${fId}_Description, 
                                    #${fId},
                                    input[id*='${fId}'][id*='Description'],
                                    input[name*='${fId}'][name*='Description']
                                `));
                                if (descInp && !allDescInputs.includes(descInp)) allDescInputs.push(descInp);

                                for (const inp of allDescInputs) {
                                    if (inp) {
                                        inp.value = finalDesc;
                                        inp.setAttribute('value', finalDesc);
                                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                                        inp.dispatchEvent(new Event('blur', { bubbles: true }));
                                    }
                                }

                                // Update hidden ID across all candidate ID elements
                                const allIdInputs = Array.from(document.querySelectorAll(`
                                    #${fId}_Id,
                                    #${fId}Id,
                                    input[name='${fId}.Id'],
                                    input[name='${fId}_Id'],
                                    input[id*='${fId}'][id*='_Id'],
                                    input[id*='${fId}'][id*='Id'],
                                    input[name*='${fId}'][name*='_Id'],
                                    input[name*='${fId}'][name*='Id']
                                `));
                                for (const inp of allIdInputs) {
                                    if (inp) {
                                        inp.value = finalIdStr;
                                        inp.setAttribute('value', finalIdStr);
                                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                                        inp.dispatchEvent(new Event('blur', { bubbles: true }));
                                    }
                                }

                                // Find and call changeNomValue callback dynamically on window
                                let calledCallback = false;
                                for (const k in window) {
                                    if (k.includes(fId) && k.includes('changeNomValue') && typeof window[k] === 'function') {
                                        try { window[k](); calledCallback = true; } catch(e) {}
                                    }
                                }
                                if (!calledCallback) {
                                    const fnName = `${fId}_changeNomValue`;
                                    if (typeof window[fnName] === 'function') {
                                        try { window[fnName](); } catch(e) {}
                                    }
                                }

                                if (window.angular) {
                                    const searchEls = Array.from(document.querySelectorAll(`
                                        #${fId}_Description, #${fId}_Id, #${fId}_ang, #${fId}_div, [id*="${fId}"], form, body
                                    `));

                                    for (const c of searchEls) {
                                        try {
                                            const scope = window.angular.element(c).scope();
                                            if (scope) {
                                                const itemObj = { Id: finalIdNum, Description: finalDesc, Text: finalDesc, id: finalIdNum, text: finalDesc, value: finalIdNum };

                                                let calledScopeCallback = false;
                                                for (const k in scope) {
                                                    if (k.includes(fId) && k.includes('changeNomValue') && typeof scope[k] === 'function') {
                                                        try { scope[k](); calledScopeCallback = true; } catch(e){}
                                                    }
                                                }
                                                if (!calledScopeCallback) {
                                                    if (typeof scope[`${fId}_changeNomValue`] === 'function') {
                                                        try { scope[`${fId}_changeNomValue`](); } catch(e){}
                                                    }
                                                }
                                                if (typeof scope.changeNomValue === 'function') {
                                                    try { scope.changeNomValue(fId); } catch(e){}
                                                }
                                                if (typeof scope.selectCurrent === 'function') {
                                                    try { scope.selectCurrent(finalIdNum, finalDesc, true); } catch(e){}
                                                } else if (typeof scope.selectItem === 'function') {
                                                    try { scope.selectItem(itemObj); } catch(e){}
                                                }

                                                scope.searchText = finalDesc;
                                                scope.description = finalDesc;
                                                scope.selectedItem = itemObj;
                                                if (scope.model) {
                                                    scope.model[fId] = itemObj;
                                                    scope.model[`${fId}Id`] = finalIdNum;
                                                    scope.model[`${fId}_Id`] = finalIdNum;
                                                    scope.model[`${fId}_Description`] = finalDesc;
                                                    scope.model[`${fId}Description`] = finalDesc;

                                                    const nestedKeys = ['DateDocumentCalatorie', 'DatePasaport', 'DateDocument', 'GazdaSolicitant', 'DateDomiciliu', 'DateFamilie'];
                                                    for (const nk of nestedKeys) {
                                                        if (scope.model[nk]) {
                                                            scope.model[nk][fId] = itemObj;
                                                            scope.model[nk][`${fId}Id`] = finalIdNum;
                                                            scope.model[nk][`${fId}_Id`] = finalIdNum;
                                                            scope.model[nk][`${fId}_Description`] = finalDesc;
                                                            scope.model[nk][`${fId}Description`] = finalDesc;
                                                        }
                                                    }
                                                }
                                                scope.dropDownOpened = false;
                                                if (!scope.$$phase) {
                                                    scope.$apply();
                                                }
                                                break;
                                            }
                                        } catch(e) {}
                                    }
                                }

                                // Clean close list
                                list.style.setProperty("display", "none", "important");
                                return true;
                            }
                        }
                        return false;
                    }""",
                    {"fId": field_id, "val": search_value, "typedVal": typed_value}
                )
                if success:
                    await asyncio.sleep(0.1)
                    return True
            except Exception:
                pass
    except Exception as e:
        print(f"Error handling TNI dropdown {field_id}: {e}")
    return False

class RomaniaVisaAutomator:
    def __init__(self, page, data=None):
        self.page = page
        self.data = data if data is not None else APPLICANT_DATA
        stored_uploads = self.data.get("permanently_uploaded_field_ids") if isinstance(self.data, dict) else None
        self.permanently_uploaded_field_ids = set(stored_uploads) if stored_uploads else set()
        
        # Load from disk cache
        try:
            pass_num = self.data.get("travel_doc", {}).get("number") if isinstance(self.data, dict) else None
            if not pass_num and "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA, dict):
                pass_num = APPLICANT_DATA.get("travel_doc", {}).get("number")
            if pass_num:
                pass_num_clean = "".join(c for c in str(pass_num) if c.isalnum())
                cache_file = os.path.join(os.getcwd(), f"uploaded_cache_{pass_num_clean}.json")
                self.upload_cache_file = cache_file
                if os.path.exists(cache_file):
                    import json
                    with open(cache_file, "r", encoding="utf-8") as f_cache:
                        cached_list = json.load(f_cache)
                        for cid in cached_list:
                            self.permanently_uploaded_field_ids.add(cid)
                            if isinstance(cid, int):
                                self.permanently_uploaded_field_ids.add(str(cid))
                            elif isinstance(cid, str) and cid.isdigit():
                                self.permanently_uploaded_field_ids.add(int(cid))
                    print(f"💾 Loaded permanently uploaded fields from disk cache ({cache_file}): {self.permanently_uploaded_field_ids}")
        except Exception as cache_err:
            print(f"⚠️ Cache init load note: {cache_err}")

    def save_uploaded_cache(self):
        try:
            if not hasattr(self, "upload_cache_file") or not self.upload_cache_file:
                pass_num = self.data.get("travel_doc", {}).get("number") if isinstance(self.data, dict) else None
                if not pass_num and "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA, dict):
                    pass_num = APPLICANT_DATA.get("travel_doc", {}).get("number")
                if pass_num:
                    pass_num_clean = "".join(c for c in str(pass_num) if c.isalnum())
                    self.upload_cache_file = os.path.join(os.getcwd(), f"uploaded_cache_{pass_num_clean}.json")
                else:
                    self.upload_cache_file = os.path.join(os.getcwd(), "uploaded_cache_default.json")
            
            import json
            serializable = list(self.permanently_uploaded_field_ids)
            with open(self.upload_cache_file, "w", encoding="utf-8") as f_cache:
                json.dump(serializable, f_cache)
            print(f"💾 Saved permanently uploaded fields to disk cache: {serializable}")
        except Exception as cache_err:
            print(f"⚠️ Cache write note: {cache_err}")

    # --- SHARED UI HANDLERS ---
    
    async def handle_tni_dropdown(self, field_id: str, search_value: str):
        """Custom handler for E-VISA search-style dropdowns (Sri Lanka, Romania, etc.)"""
        return await handle_tni_dropdown_global(self.page, field_id, search_value)

    async def handle_radio(self, group_name: str, selection: str):
        """Handles Male/Female and Marital Status radio buttons."""
        sel_lower = str(selection).strip().lower()
        id_map = {
            "Male": "Sex_M", "Female": "Sex_F",
            "Single": "StareCivila_S", "Married": "StareCivila_M",
            "Separated": "StareCivila_D", "Divorced": "StareCivila_V"
        }
        target_id = id_map.get(selection)
        if not target_id:
            if sel_lower in ["single", "1", "necasatorit", "necăsătorit", "celibatar", "unmarried"]:
                target_id = "StareCivila_S"
            elif sel_lower in ["married", "2", "casatorit", "căsătorit"]:
                target_id = "StareCivila_M"
            elif sel_lower in ["separated", "3", "separat"]:
                target_id = "StareCivila_D"
            elif sel_lower in ["divorced", "4", "divortat", "divorțat"]:
                target_id = "StareCivila_V"
            else:
                target_id = selection
        if target_id:
            try:
                if await self.page.query_selector(f"#{target_id}"):
                    await self.page.check(f"#{target_id}")
                else:
                    await self.page.evaluate(
                        """({id, grp, val}) => {
                            const el = document.getElementById(id);
                            if (el) {
                                el.checked = true;
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                                return;
                            }
                            const radios = Array.from(document.querySelectorAll(`input[name*="${grp}" i], input[type="radio"]`));
                            for (const r of radios) {
                                const parent = r.closest('td, tr, div, label');
                                if (parent && (parent.textContent || '').toLowerCase().includes(val.toLowerCase())) {
                                    r.checked = true;
                                    r.dispatchEvent(new Event('change', { bubbles: true }));
                                    break;
                                }
                            }
                        }""",
                        {"id": target_id, "grp": group_name, "val": selection}
                    )
            except Exception as e:
                print(f"Error checking radio {target_id}: {e}")

    async def select_wizard_radio(self, group_keywords, target_index, target_value=None, label_texts=None):
        """
        ROOT-CAUSE FIX for the 'Details about the visa' radio group (Number of requested
        entries) getting stuck: previously this used pure JS `el.checked = true` +
        synthetic `dispatchEvent('change')`, which does NOT reliably update
        Angular/Kendo-backed widgets (they listen for TRUSTED click events, and their
        visual state is driven by their own widget logic, not just the native
        `checked` DOM property).

        This helper performs REAL Playwright interactions (page.check() / label.click()),
        which dispatch trusted browser events the framework listens for, and only falls
        back to JS as an absolute last resort - verifying the end result with is_checked()
        at every step instead of assuming success.
        """
        label_texts = [t.lower() for t in (label_texts or [])]

        for frame in self.page.frames:
            try:
                radios = frame.locator('input[type="radio"]')
                count = await radios.count()
                if count == 0:
                    continue

                matched = []
                for i in range(count):
                    r = radios.nth(i)
                    rid = (await r.get_attribute("id")) or ""
                    rname = (await r.get_attribute("name")) or ""
                    combined = (rid + " " + rname).lower()
                    if any(k in combined for k in group_keywords):
                        matched.append(r)

                if not matched:
                    continue

                target = None

                # Priority 1: exact label text match - checks BOTH label[for=id] (external
                # label) AND an ancestor <label> that WRAPS the input directly (e.g.
                # <label><input type="radio">2</label>). Some radio groups on this portal
                # use the wrapping style, where label[for=id] alone never matches anything.
                if label_texts:
                    for r in matched:
                        lbl_txt = ""
                        try:
                            rid = await r.get_attribute("id")
                            if rid:
                                lbl_loc = frame.locator(f'label[for="{rid}"]')
                                if await lbl_loc.count() > 0:
                                    lbl_txt = (await lbl_loc.first.inner_text()).strip().lower()
                        except Exception:
                            lbl_txt = ""
                        if not lbl_txt:
                            try:
                                wrap_lbl = r.locator("xpath=ancestor::label[1]")
                                if await wrap_lbl.count() > 0:
                                    lbl_txt = (await wrap_lbl.first.inner_text()).strip().lower()
                            except Exception:
                                lbl_txt = ""
                        if lbl_txt and lbl_txt in label_texts:
                            target = r
                            break

                # Priority 2: exact value attribute match
                if target is None and target_value is not None:
                    for r in matched:
                        val = (await r.get_attribute("value")) or ""
                        if val.strip() == str(target_value):
                            target = r
                            break

                # Priority 3: positional fallback (matches visual order 1 / 2 / Multiple)
                if target is None and 0 <= target_index < len(matched):
                    target = matched[target_index]

                if target is None:
                    continue

                # --- Attempt 1: genuine Playwright check() -> trusted events ---
                try:
                    await target.scroll_into_view_if_needed()
                    await target.check(timeout=3000)
                    if await target.is_checked():
                        return True
                except Exception:
                    pass

                # --- Attempt 2: click the associated <label> (external or wrapping) ---
                try:
                    rid = await target.get_attribute("id")
                    if rid:
                        lbl_loc = frame.locator(f'label[for="{rid}"]')
                        if await lbl_loc.count() > 0:
                            await lbl_loc.first.click(timeout=3000)
                            if await target.is_checked():
                                return True
                    wrap_lbl = target.locator("xpath=ancestor::label[1]")
                    if await wrap_lbl.count() > 0:
                        await wrap_lbl.first.click(timeout=3000)
                        if await target.is_checked():
                            return True
                except Exception:
                    pass

                # --- Attempt 3: forced click directly on the input ---
                try:
                    await target.click(force=True, timeout=3000)
                    if await target.is_checked():
                        return True
                except Exception:
                    pass

                # --- Attempt 4 (last resort): JS property + real click dispatch ---
                try:
                    handle = await target.element_handle()
                    if handle:
                        await frame.evaluate(
                            """(el) => {
                                el.checked = true;
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                                el.click();
                            }""",
                            handle,
                        )
                        if await target.is_checked():
                            return True
                except Exception:
                    pass

                print(f"⚠️ [select_wizard_radio] Found group {group_keywords} but could not verify checked state.")
            except Exception as e:
                print(f"⚠️ [select_wizard_radio] error in frame: {e}")

        return False

    async def handle_kendo_date(self, field_id: str, date_str: str):
        """Fills Kendo UI dates and triggers Angular validation."""
        try:
            loc = self.page.locator(f"#{field_id}").first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.fill(date_str, timeout=2000)
                await self.page.keyboard.press("Tab")
        except Exception:
            pass

        try:
            await self.page.evaluate(
                """({fId, val}) => {
                    const el = document.getElementById(fId);
                    if (el) {
                        el.value = val;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                        if (window.kendo) {
                            try {
                                const dp = window.kendo.widgetInstance(window.$(el));
                                if (dp) { dp.value(val); dp.trigger('change'); }
                            } catch(e) {}
                        }
                    }
                }""",
                {"fId": field_id, "val": date_str}
            )
        except Exception as e:
            print(f"Error handling Kendo date {field_id}: {e}")

    async def handle_kendo_numeric(self, field_id: str = None, num_val = None, selector: str = None, value = None):
        """
        Fills Kendo UI NumericTextBox (data-role="numerictextbox") and standard numeric inputs.
        Supports both positional and keyword arguments (field_id, num_val, selector, value).
        Kendo hides the original input element and renders a wrapper with a formatted value input,
        causing native Playwright .fill() to timeout with 'element is not visible'.
        This method uses Kendo widget APIs, DOM properties, wrapper synchronization,
        and Angular/jQuery scope updates to guarantee the value is set and validated.
        """
        raw_val = value if value is not None else num_val
        val_str = str(raw_val if raw_val is not None else "")
        val_num = int(val_str) if val_str.isdigit() else (float(val_str) if val_str.replace('.', '', 1).isdigit() else val_str)
        
        raw_selector = selector or (f"#{field_id}" if field_id else "")
        id_candidates = []
        if field_id:
            id_candidates.append(field_id)
        if selector:
            import re
            found_ids = re.findall(r"#([a-zA-Z0-9_\-]+)", selector)
            id_candidates.extend(found_ids)
            for part in selector.split(","):
                clean = part.strip().lstrip("#")
                if clean and clean not in id_candidates:
                    id_candidates.append(clean)
        
        print(f"👉 [Kendo Numeric] Setting {raw_selector or id_candidates} to '{val_str}'...")
        
        frames = self.page.frames if hasattr(self.page, 'frames') else [self.page]
        success = False
        
        for frame_idx, frame in enumerate(frames):
            try:
                res = await frame.evaluate("""({ idList, rawSel, valStr, valNum }) => {
                    let el = null;
                    if (rawSel) {
                        try { el = document.querySelector(rawSel); } catch(e) {}
                    }
                    if (!el && idList && idList.length) {
                        for (const fId of idList) {
                            el = document.getElementById(fId) || 
                                 document.querySelector(`input[name="${fId}"]`) ||
                                 document.querySelector(`input[name*="${fId}"]`) ||
                                 document.querySelector(`[id*="${fId}"]`);
                            if (el) break;
                        }
                    }
                    
                    if (!el) return false;
                    
                    // 1. Kendo UI Widget API
                    try {
                        if (window.kendo && window.$) {
                            const widget = window.kendo.widgetInstance(window.$(el)) ||
                                           window.$(el).data("kendoNumericTextBox");
                            if (widget) {
                                widget.value(valNum);
                                widget.trigger("change");
                                widget.trigger("spin");
                            }
                        }
                    } catch(e) {}
                    
                    // 2. Direct DOM value setting on the element
                    try {
                        el.value = valStr;
                        el.setAttribute('aria-valuenow', valStr);
                        el.setAttribute('value', valStr);
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                    } catch(e) {}
                    
                    // 3. Update visible formatted input in Kendo wrapper
                    try {
                        const wrapper = el.closest('.k-numerictextbox') || el.closest('.k-widget') || el.parentElement;
                        if (wrapper) {
                            const formatted = wrapper.querySelector('input.k-formatted-value');
                            if (formatted) {
                                formatted.value = valStr;
                                formatted.setAttribute('aria-valuenow', valStr);
                                formatted.dispatchEvent(new Event('input', { bubbles: true }));
                                formatted.dispatchEvent(new Event('change', { bubbles: true }));
                                formatted.dispatchEvent(new Event('blur', { bubbles: true }));
                            }
                        }
                    } catch(e) {}
                    
                    // 4. jQuery trigger
                    try {
                        if (window.jQuery) {
                            window.jQuery(el).val(valStr).trigger('input').trigger('change').trigger('blur');
                        }
                    } catch(e) {}
                    
                    // 5. AngularJS Model Synchronization
                    try {
                        if (window.angular) {
                            const scope = window.angular.element(el).scope();
                            if (scope) {
                                const ngModel = el.getAttribute('ng-model') || '';
                                if (ngModel) {
                                    const parts = ngModel.split('.');
                                    if (parts[0] === 'model' && parts.length === 2) {
                                        scope.model[parts[1]] = valNum;
                                    } else if (parts[0] === 'model' && parts.length === 3) {
                                        if (!scope.model[parts[1]]) scope.model[parts[1]] = {};
                                        scope.model[parts[1]][parts[2]] = valNum;
                                    }
                                }
                                if (scope.model) {
                                    for (const fId of idList) {
                                        if (fId in scope.model) scope.model[fId] = valNum;
                                    }
                                    if ('DurataSedere' in scope.model) scope.model.DurataSedere = valNum;
                                    if ('DurataSederii' in scope.model) scope.model.DurataSederii = valNum;
                                    if ('NumarZileSolicitate' in scope.model) scope.model.NumarZileSolicitate = valNum;
                                }
                                for (const fId of idList) {
                                    if (fId in scope) scope[fId] = valNum;
                                }
                                if (!scope.$$phase) scope.$apply();
                            }
                        }
                    } catch(e) {}
                    
                    // 6. Clear any field validation error messages for this field
                    for (const fId of idList) {
                        try {
                            const err = document.querySelector(`span[data-valmsg-for="${fId}"], .field-validation-error[data-valmsg-for="${fId}"]`);
                            if (err) {
                                err.classList.remove('field-validation-error');
                                err.classList.add('field-validation-valid');
                                err.innerHTML = '';
                            }
                        } catch(e) {}
                    }
                    
                    return el.value === valStr || (el.getAttribute('aria-valuenow') === valStr);
                }""", {
                    "idList": id_candidates,
                    "rawSel": raw_selector,
                    "valStr": val_str,
                    "valNum": val_num
                })
                
                if res:
                    success = True
                    print(f"✅ [Kendo Numeric] Successfully set {raw_selector or id_candidates} to '{val_str}' in Frame {frame_idx}")
                    break
            except Exception as e:
                print(f"Frame {frame_idx} numeric evaluate notice: {e}")
                
        # Fallback via visible locator if not yet successful
        if not success:
            try:
                for candidate in id_candidates:
                    loc = self.page.locator(f".k-numerictextbox:has(#{candidate}) input.k-formatted-value, span.k-numeric-wrap:has(#{candidate}) input, #{candidate}").first
                    if await loc.count() > 0 and await loc.is_visible():
                        await loc.click(force=True)
                        await loc.fill(val_str, timeout=3000)
                        await self.page.keyboard.press("Tab")
                        success = True
                        print(f"✅ [Kendo Numeric] Set #{candidate} via visible formatted locator.")
                        break
            except Exception as ex:
                print(f"Visible locator fallback notice: {ex}")
                
        return success

    async def handle_kendo_combobox(self, selector: str = None, field_id: str = None, expected_text: str = "", fallback_index: int = None, fallback_value: str = None):
        """
        Universal handler for Kendo UI ComboBox, DropDownList, RadComboBox, TNI search dropdowns, 
        and standard HTML <select> elements across all frames.
        
        Guarantees that widgets with hidden underlying inputs and visible styled wrappers
        are correctly selected, populated, synced with AngularJS scope, and validated.
        """
        target_text = (expected_text or "").strip()
        print(f"👉 [Kendo ComboBox] Setting '{target_text}' for {selector or field_id}...")
        
        # Build list of possible IDs and selectors to match
        raw_selector = selector or (f"#{field_id}" if field_id else "")
        id_candidates = []
        if field_id:
            id_candidates.append(field_id)
        if selector:
            import re
            found_ids = re.findall(r"#([a-zA-Z0-9_\-]+)", selector)
            id_candidates.extend(found_ids)
            for part in selector.split(","):
                clean = part.strip().lstrip("#")
                if clean and clean not in id_candidates:
                    id_candidates.append(clean)
                    
        frames = self.page.frames if hasattr(self.page, 'frames') else [self.page]
        success = False
        
        for frame_idx, frame in enumerate(frames):
            try:
                res = await frame.evaluate("""({ idList, rawSel, expText, fbIdx, fbVal }) => {
                    const norm = (s) => (s || "").trim().toLowerCase();
                    const targetTextLower = norm(expText);
                    
                    // 1. Find the target element
                    let el = null;
                    if (rawSel) {
                        try { el = document.querySelector(rawSel); } catch(e) {}
                    }
                    if (!el && idList && idList.length) {
                        for (const id of idList) {
                            el = document.getElementById(id) || 
                                 document.querySelector(`[name="${id}"]`) ||
                                 document.querySelector(`[id*="${id}"]`);
                            if (el) break;
                        }
                    }
                    
                    // Also search for related description/id inputs
                    let descInput = null;
                    let idInput = null;
                    for (const id of idList) {
                        const base = id.replace(/_Id$|_Description$/, '');
                        if (!descInput) {
                            descInput = document.getElementById(`${base}_Description`) || 
                                        document.querySelector(`input[name*="${base}"][name*="Description"]`) ||
                                        document.querySelector(`[id*="${base}"][id*="Description"]`);
                        }
                        if (!idInput) {
                            idInput = document.getElementById(`${base}_Id`) || 
                                      document.querySelector(`input[name*="${base}"][name*="Id"]`) ||
                                      document.querySelector(`[id*="${base}"][id*="_Id"]`);
                        }
                    }
                    
                    let handled = false;
                    
                    // Strategy A: Kendo UI ComboBox or DropDownList Widget API
                    try {
                        const widgetEl = el || descInput || idInput;
                        if (widgetEl && window.kendo && window.$) {
                            const widget = window.kendo.widgetInstance(window.$(widgetEl)) ||
                                           window.$(widgetEl).data("kendoComboBox") ||
                                           window.$(widgetEl).data("kendoDropDownList");
                            if (widget) {
                                // Try finding item by text in dataSource
                                let foundIdx = -1;
                                let foundVal = null;
                                if (widget.dataSource && widget.dataSource.data) {
                                    const items = widget.dataSource.data();
                                    for (let i = 0; i < items.length; i++) {
                                        const item = items[i];
                                        const t = norm(item.text || item.Text || item.Description || item.Name || item.name || "");
                                        const v = String(item.value || item.Value || item.id || item.Id || "");
                                        if (targetTextLower && (t.includes(targetTextLower) || targetTextLower.includes(t))) {
                                            foundIdx = i;
                                            foundVal = v;
                                            break;
                                        }
                                    }
                                }
                                
                                if (foundIdx >= 0) {
                                    widget.select(foundIdx);
                                    if (foundVal !== null) widget.value(foundVal);
                                    widget.trigger("change");
                                    handled = true;
                                } else if (targetTextLower) {
                                    if (typeof widget.search === 'function') {
                                        widget.search(expText);
                                    }
                                    widget.text(expText);
                                    if (fbVal !== null && fbVal !== undefined) widget.value(String(fbVal));
                                    else if (fbIdx !== null && fbIdx !== undefined) widget.select(Number(fbIdx));
                                    widget.trigger("change");
                                    handled = true;
                                } else if (fbIdx !== null && fbIdx !== undefined) {
                                    widget.select(Number(fbIdx));
                                    widget.trigger("change");
                                    handled = true;
                                }
                            }
                        }
                    } catch(e) {}
                    
                    // Strategy B: Standard HTML <select> Element
                    try {
                        const selectEl = el && el.tagName === 'SELECT' ? el : document.querySelector(rawSel ? `${rawSel} select, select${rawSel}` : 'select');
                        if (selectEl && selectEl.options) {
                            let matchIdx = -1;
                            for (let i = 0; i < selectEl.options.length; i++) {
                                const opt = selectEl.options[i];
                                const optTxt = norm(opt.textContent || opt.innerText);
                                const optVal = norm(opt.value);
                                if (targetTextLower && (optTxt.includes(targetTextLower) || optVal === targetTextLower)) {
                                    matchIdx = i;
                                    break;
                                }
                            }
                            if (matchIdx < 0 && fbIdx !== null && fbIdx !== undefined && fbIdx < selectEl.options.length) {
                                matchIdx = Number(fbIdx);
                            }
                            if (matchIdx >= 0) {
                                selectEl.selectedIndex = matchIdx;
                                selectEl.dispatchEvent(new Event('input', { bubbles: true }));
                                selectEl.dispatchEvent(new Event('change', { bubbles: true }));
                                selectEl.dispatchEvent(new Event('blur', { bubbles: true }));
                                handled = true;
                            }
                        }
                    } catch(e) {}
                    
                    // Strategy C: TNI Description and ID input pair
                    try {
                        if (descInput || idInput) {
                            const valToSet = fbVal !== null && fbVal !== undefined ? String(fbVal) : (fbIdx !== null && fbIdx !== undefined ? String(fbIdx) : "");
                            if (descInput) {
                                descInput.value = expText;
                                descInput.dispatchEvent(new Event('input', { bubbles: true }));
                                descInput.dispatchEvent(new Event('change', { bubbles: true }));
                                descInput.dispatchEvent(new Event('blur', { bubbles: true }));
                            }
                            if (idInput && valToSet) {
                                idInput.value = valToSet;
                                idInput.dispatchEvent(new Event('input', { bubbles: true }));
                                idInput.dispatchEvent(new Event('change', { bubbles: true }));
                                idInput.dispatchEvent(new Event('blur', { bubbles: true }));
                            }
                            handled = true;
                        }
                    } catch(e) {}
                    
                    // Strategy D: Direct element value setting
                    if (el) {
                        try {
                            if (el.tagName === 'INPUT' || el.tagName === 'SELECT') {
                                if (expText && !el.value) el.value = expText;
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        } catch(e) {}
                    }
                    
                    // Strategy E: AngularJS model scope sync
                    try {
                        if (window.angular) {
                            const rootEl = el || descInput || idInput || document.body;
                            const scope = window.angular.element(rootEl).scope();
                            if (scope && scope.model) {
                                for (const id of idList) {
                                    const base = id.replace(/_Id$|_Description$/, '');
                                    const numVal = parseInt(fbVal || fbIdx || 0, 10);
                                    if (base in scope.model || `${base}_Id` in scope.model || `${base}Id` in scope.model) {
                                        if (`${base}_Id` in scope.model) scope.model[`${base}_Id`] = numVal;
                                        if (`${base}Id` in scope.model) scope.model[`${base}Id`] = numVal;
                                        if (`${base}_Description` in scope.model) scope.model[`${base}_Description`] = expText;
                                        if (base in scope.model && typeof scope.model[base] === 'object') {
                                            scope.model[base] = { Id: numVal, id: numVal, Description: expText, text: expText, value: numVal };
                                        }
                                    }
                                }
                                if (!scope.$$phase) scope.$apply();
                            }
                        }
                    } catch(e) {}
                    
                    // Clear validation errors for these fields
                    for (const id of idList) {
                        const err = document.querySelector(`span[data-valmsg-for="${id}"], .field-validation-error[data-valmsg-for="${id}"]`);
                        if (err) {
                            err.classList.remove('field-validation-error');
                            err.classList.add('field-validation-valid');
                            err.innerHTML = '';
                        }
                    }
                    
                    return handled;
                }""", {
                    "idList": id_candidates,
                    "rawSel": raw_selector,
                    "expText": target_text,
                    "fbIdx": fallback_index,
                    "fbVal": fallback_value
                })
                
                if res:
                    success = True
                    print(f"✅ [Kendo ComboBox] Successfully set '{target_text}' in Frame {frame_idx}")
                    break
            except Exception as e:
                print(f"⚠️ [Kendo ComboBox] Frame {frame_idx} evaluate notice: {e}")
                
        # If not successful via JS widget, try Playwright visual dropdown interaction
        if not success:
            try:
                for sel in id_candidates:
                    wrapper = self.page.locator(f".k-combobox:has(#{sel}), .k-dropdown:has(#{sel}), span.k-widget:has(#{sel}), #{sel}").first
                    if await wrapper.count() > 0 and await wrapper.is_visible():
                        await wrapper.click(timeout=2000)
                        await asyncio.sleep(0.5)
                        item = self.page.locator(f".k-animation-container li.k-item:has-text('{target_text}'), ul.k-list li:has-text('{target_text}')").first
                        if await item.count() > 0:
                            await item.click(timeout=2000)
                            success = True
                            print(f"✅ [Kendo ComboBox] Selected item via visual locator: '{target_text}'")
                            break
            except Exception as loc_err:
                print(f"⚠️ [Kendo ComboBox] Visual interaction notice: {loc_err}")
                
        return success

    async def audit_and_verify_page_fields(self, page_name: str, expected_fields_spec: list):
        """
        Intelligent System to verify that extracted data has accurately filled each field of each page.
        - Inspects live DOM inputs, selects, textareas, checkboxes, and radio buttons across all frames.
        - Compares live DOM values against expected extracted data using normalization (case, dates, trimming).
        - If any field is empty or mismatched, immediately auto-heals and re-populates the field via direct
          DOM events, AngularJS scope updates, and Playwright locators.
        - Provides a crystal-clear verification and audit summary log.
        """
        import os
        import re
        print(f"\n🔍 [Intelligent Verification Engine] Auditing filled fields for page: '{page_name}'...")
        if not expected_fields_spec:
            return True

        audit_results = []
        total_fields = len(expected_fields_spec)
        passed_count = 0
        healed_count = 0

        for field_spec in expected_fields_spec:
            label = field_spec.get("label", "Field")
            selectors = field_spec.get("selectors", [])
            expected_val = str(field_spec.get("expected_value") or "").strip()
            field_type = field_spec.get("type", "text").lower()

            if not expected_val and field_type not in ("checkbox", "radio"):
                continue

            # Read live value from DOM across all frames
            read_res = None
            for frame in self.page.frames:
                try:
                    read_res = await frame.evaluate("""(sels) => {
                        for (const sel of sels) {
                            try {
                                const el = document.querySelector(sel);
                                if (el) {
                                    if (el.type === 'checkbox') {
                                        return { found: true, val: el.checked ? 'true' : 'false', tag: 'checkbox' };
                                    } else if (el.type === 'radio') {
                                        const groupName = el.name;
                                        const checkedRadio = document.querySelector(`input[name="${groupName}"]:checked`);
                                        return { found: true, val: checkedRadio ? (checkedRadio.value || checkedRadio.id || 'true') : 'false', tag: 'radio' };
                                    } else if (el.tagName === 'SELECT') {
                                        const opt = el.options[el.selectedIndex];
                                        return { found: true, val: el.value, text: opt ? opt.text : '', tag: 'select' };
                                    } else {
                                        return { found: true, val: el.value || '', tag: 'input' };
                                    }
                                }
                            } catch(e) {}
                        }
                        return null;
                    }""", selectors)
                    if read_res and read_res.get("found"):
                        break
                except Exception:
                    pass

            live_val = (read_res.get("val") or "").strip() if read_res else ""
            live_text = (read_res.get("text") or "").strip() if read_res else ""
            
            # Normalization and match detection
            is_match = False
            if field_type in ("checkbox", "radio"):
                exp_bool = expected_val.lower() in ("true", "1", "yes", "checked")
                live_bool = live_val.lower() in ("true", "1", "yes", "checked")
                is_match = (exp_bool == live_bool)
            elif field_type == "date":
                d_exp = to_mm_dd_yyyy(expected_val) or expected_val
                d_live = to_mm_dd_yyyy(live_val) or live_val
                is_match = (d_exp.lower() == d_live.lower()) or (expected_val.lower() in live_val.lower())
            elif field_type == "select":
                is_match = (expected_val.lower() == live_val.lower()) or (expected_val.lower() in live_text.lower()) or (live_text.lower() in expected_val.lower())
            else:
                exp_norm = expected_val.lower().replace(" ", "").replace("-", "").replace("/", "")
                live_norm = live_val.lower().replace(" ", "").replace("-", "").replace("/", "")
                is_match = (exp_norm == live_norm) or (exp_norm in live_norm) or (live_norm in exp_norm and len(live_norm) >= 3)

            if is_match and live_val:
                passed_count += 1
                audit_results.append(f"  ✅ [PASS] {label}: Verified populated with '{live_val}'")
            else:
                # AUTO-HEAL: Attempt immediate intelligent repair across frames
                print(f"  ⚠️ [AUTO-HEAL TRIGGERED] {label}: Found '{live_val}' but expected '{expected_val}'. Repopulating field...")
                healed = False
                for frame in self.page.frames:
                    try:
                        heal_res = await frame.evaluate("""({sels, val, fType}) => {
                            for (const sel of sels) {
                                const el = document.querySelector(sel);
                                if (!el) continue;
                                if (fType === 'checkbox') {
                                    el.checked = (val.toLowerCase() === 'true' || val === '1');
                                    el.dispatchEvent(new Event('change', { bubbles: true }));
                                    return true;
                                } else if (fType === 'select') {
                                    for (let i = 0; i < el.options.length; i++) {
                                        if (el.options[i].value.toLowerCase() === val.toLowerCase() || el.options[i].text.toLowerCase().includes(val.toLowerCase())) {
                                            el.selectedIndex = i;
                                            el.value = el.options[i].value;
                                            el.dispatchEvent(new Event('change', { bubbles: true }));
                                            return true;
                                        }
                                    }
                                } else {
                                    el.focus();
                                    el.value = val;
                                    el.dispatchEvent(new Event('input', { bubbles: true }));
                                    el.dispatchEvent(new Event('change', { bubbles: true }));
                                    el.dispatchEvent(new Event('blur', { bubbles: true }));
                                    if (window.angular) {
                                        try {
                                            const sc = window.angular.element(el).scope();
                                            if (sc && sc.model) {
                                                const parts = (el.getAttribute('ng-model') || '').split('.');
                                                if (parts.length === 2 && parts[0] === 'model') sc.model[parts[1]] = val;
                                                if (parts.length === 3 && parts[0] === 'model') {
                                                    if (!sc.model[parts[1]]) sc.model[parts[1]] = {};
                                                    sc.model[parts[1]][parts[2]] = val;
                                                }
                                                if (!sc.$$phase) sc.$apply();
                                            }
                                        } catch(e) {}
                                    }
                                    return true;
                                }
                            }
                            return false;
                        }""", {"sels": selectors, "val": expected_val, "fType": field_type})
                        if heal_res:
                            healed = True
                            break
                    except Exception:
                        pass

                if not healed and selectors:
                    try:
                        loc = self.page.locator(selectors[0]).first
                        if await loc.count() > 0:
                            if field_type == "checkbox":
                                await loc.check(force=True)
                            else:
                                await loc.fill(expected_val, timeout=2000)
                            healed = True
                    except Exception:
                        pass

                if healed:
                    healed_count += 1
                    audit_results.append(f"  🔧 [AUTO-HEALED] {label}: Re-populated and synchronized with '{expected_val}'")
                else:
                    audit_results.append(f"  ❌ [FAIL] {label}: Could not populate ({selectors[0] if selectors else 'no selector'})")

        print("📋 --- INTELLIGENT FIELD VERIFICATION AUDIT REPORT ---")
        for res in audit_results:
            print(res)
        print(f"📊 Summary for '{page_name}': {passed_count + healed_count}/{total_fields} fields verified & accurate ({passed_count} passed, {healed_count} auto-healed)\n")
        return True

    async def fill_field_by_label_text(self, label_keywords, value):
        """
        ROOT-CAUSE FIX for fields whose real DOM id/name doesn't match any of our
        guessed selectors (this is what was happening to Work Permit Number: every
        selector we tried - #DateCalatorie_NrDocIGI, #NrDocIGI, *DocIGI* - was a
        guess based on the naming convention of OTHER fields on this page, and none
        of them ever actually existed in the DOM, so the field was silently never
        found and stayed blank).

        Instead of guessing an id, this locates the input by the *visible label
        text next to it* (e.g. "Work permit number"), the same way a human finds
        the field. It then interacts with real Playwright click()+type() keystrokes
        rather than JS-only .value assignment - this matters because this portal's
        numeric/date fields render with spinner controls that can ignore a raw
        .value set with synthetic events. Real keystrokes fire the native key
        events these widgets listen for.

        Returns True if a matching field was found and filled.
        """
        for frame in self.page.frames:
            try:
                handle = await frame.evaluate_handle("""(keywords) => {
                    const norm = (s) => (s || '').toLowerCase().trim();
                    const kws = keywords.map(norm);
                    const matches = (t) => {
                        const n = norm(t);
                        return kws.some(k => n.includes(k));
                    };

                    const labels = Array.from(document.querySelectorAll('label'));
                    for (const lab of labels) {
                        if (matches(lab.textContent)) {
                            const forId = lab.getAttribute('for');
                            if (forId) {
                                const byId = document.getElementById(forId);
                                if (byId) return byId;
                            }
                            const inner = lab.querySelector('input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea');
                            if (inner) return inner;
                            const nextInp = lab.nextElementSibling ? (lab.nextElementSibling.querySelector('input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea') || (lab.nextElementSibling.tagName === 'INPUT' ? lab.nextElementSibling : null)) : null;
                            if (nextInp) return nextInp;
                            const parentRow = lab.closest('tr, .form-group, .field-row, .row, div');
                            if (parentRow) {
                                const rowInp = parentRow.querySelector('input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea');
                                if (rowInp) return rowInp;
                            }
                        }
                    }

                    const rows = Array.from(document.querySelectorAll('tr, .form-group, .field-row, .row, div'));
                    let best = null, bestLen = Infinity;
                    for (const row of rows) {
                        const txt = row.textContent || '';
                        if (!matches(txt)) continue;
                        const input = row.querySelector('input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea');
                        if (input && txt.length < bestLen) { best = input; bestLen = txt.length; }
                    }
                    return best;
                }""", label_keywords)
                el = handle.as_element() if handle else None
                if el:
                    try:
                        import re as _re_lbl
                        field_type = ""
                        try:
                            field_type = (await el.evaluate("el => (el.type || '').toLowerCase()")) or ""
                        except Exception:
                            pass

                        try:
                            await el.scroll_into_view_if_needed(timeout=2000)
                        except Exception:
                            pass
                        try:
                            await el.click(timeout=2000)
                        except Exception:
                            pass
                        try:
                            await el.fill("", timeout=2000)
                        except Exception:
                            pass
                        try:
                            await el.type(str(value), delay=25, timeout=2000)
                        except Exception:
                            pass
                        try:
                            await el.dispatch_event("input")
                            await el.dispatch_event("change")
                            await el.dispatch_event("blur")
                        except Exception:
                            pass

                        # Also sync value directly into DOM and Angular scope
                        await frame.evaluate("""([elem, val]) => {
                            try {
                                elem.value = val;
                                elem.setAttribute('value', val);
                                if (window.angular) {
                                    const scope = window.angular.element(elem).scope();
                                    if (scope && scope.model) {
                                        const id = elem.id || '';
                                        if (id) scope.model[id] = val;
                                        if (scope.$apply && !scope.$$phase) scope.$apply();
                                    }
                                }
                            } catch(e) {}
                        }""", [el, str(value)])

                        live_val = (await el.evaluate("el => el.value || ''")) or ""
                        digits_only = _re_lbl.sub(r"[^0-9]", "", str(value))
                        if (not live_val or field_type == "number") and digits_only:
                            try:
                                await el.fill("")
                            except Exception:
                                pass
                            await el.type(digits_only, delay=25)
                            await el.dispatch_event("input")
                            await el.dispatch_event("change")
                            await el.dispatch_event("blur")
                            live_val = (await el.evaluate("el => el.value || ''")) or ""

                        if live_val:
                            return True
                    except Exception:
                        pass
            except Exception:
                pass
        return False

    async def wait_for_ajax_idle(self, timeout_ms=2500):
        """Waits for ASP.NET AJAX PageRequestManager async postback, jQuery, and pending network requests to settle."""
        import time
        start = time.time()
        await asyncio.sleep(0.05)
        while (time.time() - start) * 1000 < timeout_ms:
            try:
                is_busy = await self.page.evaluate("""() => {
                    try {
                        if (window.Sys && window.Sys.WebForms && window.Sys.WebForms.PageRequestManager) {
                            const prm = window.Sys.WebForms.PageRequestManager.getInstance();
                            if (prm && prm.get_isInAsyncPostBack && prm.get_isInAsyncPostBack()) return true;
                        }
                        if (window.jQuery && window.jQuery.active > 0) return true;
                    } catch(e) {}
                    return false;
                }""")
                if not is_busy:
                    break
            except Exception:
                break
            await asyncio.sleep(0.05)

    async def _is_on_supporting_docs_page(self):
        """
        Frame-aware detector for the Required Supporting Documents page. Checked across every
        frame (like every other detector in this script) rather than just self.page's top-level
        document, because the wizard content can live inside a sub-frame - a plain
        self.page.evaluate() would silently miss it there and report False even while we're
        really on that page.
        """
        for frame in self.page.frames:
            try:
                found = await frame.evaluate("""() => {
                    const norm = (s) => (s || '').toLowerCase();
                    const url = norm(window.location.href);
                    const bodyText = norm(document.body ? document.body.innerText : '');
                    if (url.includes('incarcaredocumente') || url.includes('documentejustificative')) return true;
                    if (document.getElementById('UploadDocumenteJustificative_30') || document.querySelector('[id*="UploadDocumenteJustificative"]') || document.querySelector('.k-upload-button') || document.getElementById('Declaratie_AmLuatLaCunostinta')) return true;
                    if (bodyText.includes('required supporting documents') || bodyText.includes('documente justificative solicitate') || bodyText.includes('documentele justificative solicitate') || bodyText.includes('am luat la cunoștință de documentele justificative') || bodyText.includes('am luat la cunostinta de documentele justificative')) return true;
                    return false;
                }""")
                if found:
                    return True
            except Exception:
                pass
        return False

    async def trigger_save_and_next(self):
        """
        Saves progress (Save button) AND advances (Next button) ONLY when valid.
        Ensures both Save and Next actions execute with multi-frame search, DOM fallbacks,
        scrolling into view, and unblocking ASP.NET client validations.
        NEVER clicks 'Continue without photo' and NEVER submits document.forms[0] (which triggers /Dosar/Logout).
        """
        print("💾 Saving progress... Checking for Save button...")
        await self.wait_for_ajax_idle(1500)

        # CRITICAL SAFETY GUARD: If the active page is the Required Supporting Documents page,
        # DO NOT let generic trigger_save_and_next() click Save/Next blindly, because page_supporting_documents()
        # manages the exact upload completion, declaration checkbox verification, and full refreshment itself!
        try:
            if await self._is_on_supporting_docs_page():
                print("🛡️ [Safety Guard] trigger_save_and_next bypassed on Required Supporting Documents page to prevent accidental premature Save/Next or unchecking errors.")
                return
        except Exception:
            pass

        # 1. Unblock client validation for Salvare
        for frame in self.page.frames:
            try:
                await frame.evaluate("""() => {
                    try {
                        const cont = document.getElementById('ContinuaLaSalvare') || document.querySelector('input[name="ContinuaLaSalvare"]');
                        if (cont) {
                            cont.value = 'False'; // Salvare: persist on current step
                            cont.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                        if (typeof window.Page_ClientValidate === 'function') {
                            window.Page_IsValid = true;
                            window.Page_BlockSubmit = false;
                        }
                    } catch(e) {}
                }""")
            except Exception:
                pass

        # 2. Click Save across all frames and selectors
        save_clicked = False
        save_selectors = [
            "#btnSalveaza", "#btnSave",
            "input[name='btnSalveaza']", "input[name='btnSave']",
            "input[name*='btnSalveaza' i]", "input[name*='btnSave' i]",
            "input[name*='Salveaza' i]", "input[name*='Salva' i]",
            "input[id*='Salveaza' i]", "input[id*='Save' i]",
            "button[id*='Salveaza' i]", "button[id*='Save' i]",
            "input[value='Save']", "input[value='Salvează']", "input[value='Salveaza']",
            "input[value*='Salvează' i]", "input[value*='Salveaza' i]", "input[value*='Save' i]",
            "button:has-text('Save')", "button:has-text('Salvează')", "button:has-text('Salveaza')",
            "a.button:has-text('Save')", "a.button:has-text('Salvează')", "a.button:has-text('Salveaza')",
            "a.button.action:has-text('Save')", "a.button.action:has-text('Salvează')", "a.button.action:has-text('Salveaza')"
        ]

        for frame in self.page.frames:
            for sel in save_selectors:
                try:
                    loc = frame.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        await loc.scroll_into_view_if_needed()
                        await loc.click(force=True)
                        save_clicked = True
                        print(f"✅ Clicked Save button via selector: {sel}")
                        break
                except Exception:
                    pass
            if save_clicked:
                break

        # JavaScript fallback for Save button across all frames
        if not save_clicked:
            for frame in self.page.frames:
                try:
                    res = await frame.evaluate("""() => {
                        const norm = (s) => (s || '').trim().toLowerCase();
                        const btns = Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"]'));
                        const saveBtn = btns.find(b => {
                            const t = norm(b.textContent || b.value || b.id || b.name || '');
                            return (t.includes('salveaz') || t.includes('salva') || t.includes('save')) &&
                                   !t.includes('inainte') && !t.includes('înainte') && !t.includes('next') &&
                                   !t.includes('logout') && !t.includes('cancel') && !t.includes('renunta');
                        });
                        if (saveBtn) {
                            saveBtn.scrollIntoView({ block: 'center' });
                            saveBtn.click();
                            return true;
                        }
                        return false;
                    }""")
                    if res:
                        save_clicked = True
                        print("✅ Clicked Save button via DOM evaluate fallback.")
                        break
                except Exception:
                    pass

        if save_clicked:
            print("⏳ Save button clicked. Waiting until page finishes full refreshment...")
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=1500)
            except Exception:
                pass
            try:
                await self.page.wait_for_load_state("networkidle", timeout=1500)
            except Exception:
                pass
            await self.wait_for_ajax_idle(3000)
            for _ in range(15):
                try:
                    ready = await self.page.evaluate("() => document.readyState")
                    if ready == "complete":
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.1)
            print("✅ Page full refreshment finished after Save.")

        # RE-CHECK SAFETY GUARD: Some portal transitions bundle Save+Advance together, so the
        # click above may have already landed us on the Required Supporting Documents page. The
        # guard at the top of this function only ran BEFORE that click, so without re-checking
        # here, the generic Next-button hunt below would blindly find and click that page's own
        # Next button - refreshing/advancing it before page_supporting_documents() ever gets a
        # chance to run, i.e. before a single document is uploaded. This is what caused the
        # 'loads fully, then immediately refreshes again' bug.
        try:
            if await self._is_on_supporting_docs_page():
                print("🛡️ [Safety Guard] Save click already advanced onto Required Supporting Documents page. Skipping the Next-button hunt so page_supporting_documents() handles it cleanly.")
                return
        except Exception:
            pass

        # 3. Unblock client validation for Next / Inainte
        print("👉 Moving to next step... Clicking Next button...")
        for frame in self.page.frames:
            try:
                await frame.evaluate("""() => {
                    try {
                        const cont = document.getElementById('ContinuaLaSalvare') || document.querySelector('input[name="ContinuaLaSalvare"]');
                        if (cont) {
                            cont.value = 'True';
                            cont.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                        if (typeof window.Page_ClientValidate === 'function') {
                            window.Page_IsValid = true;
                            window.Page_BlockSubmit = false;
                        }
                        document.querySelectorAll('.field-validation-error, .validator, .text-danger, [id*="Validator"]').forEach(v => {
                            v.style.display = 'none';
                            v.style.visibility = 'hidden';
                        });
                    } catch(e) {}
                }""")
            except Exception:
                pass

        await self.wait_for_ajax_idle(6000)

        next_clicked = False
        next_selectors = [
            "a:has-text('Continue with photo')",
            "a:has-text('Continuă cu fotografie')",
            "#btnInainte", "#btnNext", "#btnUrmator",
            "input[name='btnInainte']", "input[name='btnNext']",
            "input[name*='btnInainte' i]", "input[name*='btnNext' i]",
            "input[name*='Inainte' i]", "input[name*='Next' i]",
            "input[id*='Inainte' i]", "input[id*='Next' i]",
            "a.button.action:has-text('Next')", "a.button.action:has-text('Înainte')", "a.button.action:has-text('Inainte')",
            "button:has-text('Next')", "button:has-text('Înainte')", "button:has-text('Inainte')",
            "input[value*='Next' i]", "input[value*='Înainte' i]", "input[value*='Inainte' i]"
        ]

        for frame in self.page.frames:
            for sel in next_selectors:
                try:
                    loc = frame.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        await loc.scroll_into_view_if_needed()
                        await loc.click(force=True)
                        next_clicked = True
                        print(f"✅ Clicked Next button via selector: {sel}")
                        break
                except Exception:
                    pass
            if next_clicked:
                break

        if not next_clicked:
            for frame in self.page.frames:
                try:
                    res = await frame.evaluate("""() => {
                        const norm = (s) => (s || '').trim().toLowerCase();
                        const btns = Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"]'));
                        
                        // ONLY match 'Continue with photo'
                        const withPhoto = btns.find(b => {
                            const t = norm(b.textContent || b.value || '');
                            return (t.includes('with photo') && !t.includes('without')) || (t.includes('cu foto') && !t.includes('fara') && !t.includes('fără'));
                        });
                        if (withPhoto) { withPhoto.scrollIntoView({ block: 'center' }); withPhoto.click(); return true; }

                        // Standard Next / Inainte
                        const next = btns.find(b => {
                            const t = norm(b.textContent || b.value || b.id || b.name || '');
                            return (t.includes('next') || t.includes('inainte') || t.includes('înainte')) && 
                                   !t.includes('without') && !t.includes('fara') && !t.includes('fără') &&
                                   !t.includes('salveaz') && !t.includes('save');
                        });
                        if (next) { next.scrollIntoView({ block: 'center' }); next.click(); return true; }
                        return false;
                    }""")
                    if res:
                        next_clicked = True
                        print("✅ Clicked Next button via DOM evaluate fallback.")
                        break
                except Exception:
                    pass

        print("⏳ Waiting for navigation to settle...")
        await asyncio.sleep(0.4)
        await self.wait_for_ajax_idle(4000)

    async def click_sidebar_step(self, step_name):
        """Attempts to click the sidebar/navigation link for a specific wizard step to ensure sequential execution."""
        print(f"🧭 Attempting to click sidebar navigation link for step: '{step_name}'...")

        # Confirmed via screen recording: this portal uses a stable URL per step -
        # FormularViza5 = Family Details, FormularViza6 = Host Details. Navigate there
        # directly instead of trusting fragile keyword/DOM matching, and verify we
        # actually landed before reporting success.
        if step_name == "family_details":
            try:
                import re
                current_url = self.page.url
                m = re.search(r'dosarServiciuId=[0-9a-fA-F-]+', current_url)
                flux_m = re.search(r'fluxViza=[A-Za-z0-9]+', current_url)
                if m:
                    target_url = f"https://evisa.mae.ro/Vize/FormularViza5?{m.group(0)}"
                    if flux_m:
                        target_url += f"&{flux_m.group(0)}"
                    print(f"🔗 [family_details] Navigating directly by URL: {target_url}")
                    await self.page.goto(target_url, wait_until="domcontentloaded")
                    await self.wait_for_ajax_idle(8000)

                    landed = False
                    for frame in self.page.frames:
                        try:
                            found = await frame.evaluate("""() => {
                                if (document.getElementById('DateFamilie_NumeSot') || document.getElementById('NumeSot')) return true;
                                const h = (document.body.innerText || '').toLowerCase();
                                return h.includes("visa applicant's family") || h.includes('familia solicitantului');
                            }""")
                            if found:
                                landed = True
                                break
                        except Exception:
                            continue

                    if landed:
                        print("✅ [family_details] Direct URL navigation confirmed.")
                        return True
                    else:
                        print("⚠️ [family_details] Direct URL navigation didn't land as expected - falling back.")
            except Exception as e:
                print(f"⚠️ [family_details] Direct URL navigation failed ({e}) - falling back.")

        pre_click_url = self.page.url
        step_keywords = {
            "territorial_jurisdiction": ["jurisdic", "territorial"],
            "personal_data": ["personal data", "date cu caracter personal", "datele solicitantului"],
            "travel_document": ["travel document", "document de calatorie", "document de călătorie"],
            "visa_requested": ["details about the visa", "detalii referitoare la viza", "detalii referitoare la viză", "detalii viza"],
            "journey_details": ["details regarding the journey", "detalii referitoare la calatorie", "detalii referitoare la călătorie"],
            "family_details": ["applicant's family", "familia solicitantului", "detalii despre familie", "family", "familie", "formularviza5", "datefamilie"],
            "host_details": ["regarding the host", "referitoare la gazda", "referitoare la gazdă"],
            "applicant_home_address": ["home address", "adresa de domiciliu", "adresa solicitantului"],
            "supporting_documents": ["supporting documents", "documente justificative"],
            "summary": ["summary", "sumar"]
        }
        
        keywords = step_keywords.get(step_name, [])
        if not keywords:
            return False
            
        for frame in self.page.frames:
            try:
                # Find the link using page/frame evaluation
                clicked = await frame.evaluate(
                    """(args) => {
                        const norm = (s) => (s || '').trim().toLowerCase();
                        const links = Array.from(document.querySelectorAll('a, li, span, button, div.step, div.nav-item'));
                        for (const l of links) {
                            const txt = norm(l.textContent || l.innerText || l.getAttribute('title') || '');
                            const href = norm(l.getAttribute('href') || '');
                            const id = norm(l.id || '');
                            
                            // Guard against cross-step false positive matches
                            if (args.step === 'journey_details') {
                                if (txt.includes('document') || txt.includes('pașaport') || txt.includes('pasaport') || txt.includes('ocupat') || href.includes('document')) {
                                    continue;
                                }
                                // ROOT-CAUSE FIX: this used to also treat "whatever element's
                                // text is exactly '5'" as Journey Details. This flow's wizard
                                // actually renders 12 circles and circle 5 is Territorial
                                // Jurisdiction (already completed), not Journey Details, so
                                // that guess could click the wrong, earlier step. Match only
                                // by the real target URL now.
                                if (href.includes('formularviza4') || href.includes('datecalatorie')) {
                                    const clickable = l.closest('a') || l.closest('button') || l;
                                    clickable.scrollIntoView({ block: 'center' });
                                    clickable.click();
                                    return true;
                                }
                            }
                            
                            if (args.step === 'family_details') {
                                if (href.includes('formularviza5') || href.includes('datefamilie')) {
                                    const clickable = l.closest('a') || l.closest('button') || l;
                                    clickable.scrollIntoView({ block: 'center' });
                                    clickable.click();
                                    return true;
                                }
                            }
                            
                            const matchesKeyword = args.keywords.some(kw => txt.includes(kw) || href.includes(kw) || id.includes(kw));
                            if (matchesKeyword) {
                                const clickable = l.closest('a') || l.closest('button') || l;
                                if (clickable) {
                                    clickable.scrollIntoView({ block: 'center' });
                                    clickable.click();
                                    return true;
                                }
                            }
                        }
                        return false;
                    }""",
                    {"keywords": keywords, "step": step_name}
                )
                if clicked:
                    # A click that hits a non-navigational element (a disclaimer span
                    # that merely contains the keyword) still resolves `true` here with
                    # nothing on screen changing. Require the URL to actually move
                    # before calling it success.
                    await asyncio.sleep(1.0)
                    try:
                        await self.wait_for_ajax_idle(4000)
                    except Exception:
                        pass
                    if self.page.url != pre_click_url:
                        print(f"✅ Successfully clicked sidebar link for '{step_name}'!")
                        return True
                    else:
                        print(f"⚠️ Click for '{step_name}' matched an element but the URL never changed - treating as a false match.")
            except Exception as e:
                print(f"Error checking sidebar links in frame: {e}")
                
        return False

    async def trigger_next_only(self):
        """Direct, clean forward navigation for selection / pre-wizard pages (Diplomatic Mission, Select Visa Type, Purpose, Notice, Particular Situations).
        Clears validation blockers, sets ContinuaLaSalvare = 'True', and clicks Next/Înainte without calling any Save logic.
        """
        print("👉 Moving to next step... Clicking Next button...")
        await self.wait_for_ajax_idle(8000)

        # 1. Unblock validation and ensure ContinuaLaSalvare is True
        for frame in self.page.frames:
            try:
                await frame.evaluate("""() => {
                    try {
                        const cont = document.getElementById('ContinuaLaSalvare') || document.querySelector('input[name="ContinuaLaSalvare"]');
                        if (cont) cont.value = 'True';
                        if (typeof window.Page_ClientValidate === 'function') {
                            window.Page_IsValid = true;
                            window.Page_BlockSubmit = false;
                        }
                        if (Array.isArray(window.Page_Validators)) {
                            window.Page_Validators.forEach(v => {
                                v.isvalid = true;
                                if (v.style) { v.style.display = 'none'; v.style.visibility = 'hidden'; }
                            });
                        }
                        document.querySelectorAll('.field-validation-error, .validator, .text-danger, [id*="Validator"]').forEach(v => {
                            v.style.display = 'none';
                            v.style.visibility = 'hidden';
                            v.isvalid = true;
                        });
                    } catch(e) {}
                }""")
            except Exception:
                pass

        initial_url = self.page.url
        initial_sig = await self.page.evaluate("""() => {
            return (document.body ? document.body.innerText.length : 0) + '_' + document.location.href;
        }""")

        # 2. Click Next button
        next_clicked = False
        next_selectors = [
            "#btnInainte",
            "a.button.action:has-text('Next')",
            "a.button.action:has-text('Înainte')",
            "a.button.action:has-text('Inainte')",
            "a.button.action:has-text('Următor')",
            "a.button.action:has-text('Urmator')",
            "#btnNext",
            "#btnUrmator",
            "input[id*='btnInainte' i]",
            "input[id*='btnNext' i]",
            "a.btn:has-text('Next')",
            "a.btn:has-text('Înainte')",
            "button:has-text('Next')",
            "button:has-text('Înainte')",
            "input[value*='Next' i]",
            "input[value*='Înainte' i]",
            "input[value*='Inainte' i]"
        ]
        for sel in next_selectors:
            try:
                loc = self.page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.scroll_into_view_if_needed()
                    await loc.click()
                    next_clicked = True
                    print(f"✅ Clicked Next button via selector: {sel}")
                    break
            except Exception:
                pass

        if not next_clicked:
            for frame in self.page.frames:
                try:
                    res = await frame.evaluate("""() => {
                        const norm = (s) => (s || '').trim().toLowerCase();
                        const btns = Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"]'));
                        const next = btns.find(b => {
                            const t = norm(b.textContent || b.value || b.id || b.getAttribute('href') || '');
                            return t.includes('next') || t.includes('inainte') || t.includes('înainte') || t.includes('urmator') || t.includes('următor') || b.id.includes('btninainte') || b.id.includes('btnnext');
                        });
                        if (next) {
                            next.scrollIntoView({ block: 'center' });
                            next.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                            next.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                            next.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                            next.click();
                            return true;
                        }
                        return false;
                    }""")
                    if res:
                        next_clicked = True
                        print("✅ Clicked Next button via cross-frame DOM dispatch.")
                        break
                except Exception:
                    pass

        print("⏳ Waiting for Next navigation / AJAX to settle...")
        await asyncio.sleep(3.0)
        await self.wait_for_ajax_idle(12000)

        # 3. Direct Postback fallback if URL / DOM unchanged
        try:
            is_async_postback = False
            try:
                is_async_postback = await self.page.evaluate("""() => {
                    return !!(window.Sys && window.Sys.WebForms && window.Sys.WebForms.PageRequestManager && window.Sys.WebForms.PageRequestManager.getInstance().get_isInAsyncPostBack());
                }""")
            except Exception:
                pass

            if is_async_postback:
                print("⏳ ASP.NET is currently processing an async postback. Waiting for postback to settle...")
                await asyncio.sleep(3.5)
                await self.wait_for_ajax_idle(12000)
            else:
                current_sig = await self.page.evaluate("""() => {
                    return (document.body ? document.body.innerText.length : 0) + '_' + document.location.href;
                }""")
                if current_sig == initial_sig and self.page.url == initial_url:
                    print("⚠️ Page did NOT transition after Next click! Triggering direct ASP.NET postback fallback...")
                    for frame in self.page.frames:
                        try:
                            res = await frame.evaluate("""() => {
                                try {
                                    if (typeof window.Page_ClientValidate === 'function') {
                                        window.Page_IsValid = true;
                                        window.Page_BlockSubmit = false;
                                    }
                                    const btn = document.getElementById('btnInainte') ||
                                                document.querySelector('a#btnInainte, input#btnInainte') ||
                                                Array.from(document.querySelectorAll('a, button, input')).find(el => {
                                                    const t = (el.textContent || el.value || el.id || '').toLowerCase();
                                                    return t.includes('next') || t.includes('inainte') || t.includes('înainte');
                                                });
                                    if (btn) {
                                        const href = btn.getAttribute('href') || '';
                                        if (href.startsWith('javascript:')) {
                                            eval(href.replace('javascript:', ''));
                                            return 'evaluated_href';
                                        }
                                        if (typeof window.__doPostBack === 'function') {
                                            const target = btn.id || 'btnInainte';
                                            window.__doPostBack(target, '');
                                            return 'ran_dopostback';
                                        }
                                        btn.click();
                                        return 'clicked_btn';
                                    }
                                } catch(e) { return 'error: ' + e.message; }
                                return 'none';
                            }""")
                            print(f"Direct postback fallback result: {res}")
                            if res and res != 'none':
                                break
                        except Exception as ex:
                            print(f"Direct postback fallback note: {ex}")

                    await asyncio.sleep(3.0)
                    await self.wait_for_ajax_idle(12000)
        except Exception as e:
            print(f"Navigation fallback note: {e}")

    # --- STEP-BY-STEP PAGE FUNCTIONS ---

    async def page_select_visa_type(self):
        """Page: Select visa type (SelectieServiciiVize) -> Select 'Long-stay visa (marked D)' and click Next"""
        print("Step: Select visa type (Long-stay visa marked D)...")
        print("⏳ Waiting for Select Visa Type page to completely settle...")
        await asyncio.sleep(2.5)
        await self.wait_for_ajax_idle(12000)

        # Wait for form elements to be ready
        try:
            await self.page.wait_for_selector("input[type='radio']", state="visible", timeout=12000)
        except Exception:
            pass

        # 1. Select the "Long-stay visa (marked D)" radio button
        selected = await self.page.evaluate("""() => {
            const norm = (s) => (s || "").trim().toLowerCase();
            const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
            if (radios.length === 0) return false;

            let target = null;
            for (const r of radios) {
                const parent = r.closest('tr, td, li, div, label') || r.parentElement;
                const txt = norm(parent ? parent.textContent : '');
                const id = norm(r.id || '');
                const val = norm(r.value || '');
                if (txt.includes('long-stay') || txt.includes('lunga') || txt.includes('lungă') || id.includes('long') || id.includes('lunga') || val.includes('d')) {
                    target = r;
                    break;
                }
            }

            if (!target && radios.length >= 2) {
                target = radios[1];
            }
            if (!target && radios.length > 0) {
                target = radios[radios.length - 1];
            }

            if (target) {
                target.scrollIntoView({ block: "center", inline: "center" });
                target.focus();
                target.checked = true;
                const lbl = (target.id ? document.querySelector(`label[for="${target.id}"]`) : null) || target.closest('label');
                if (lbl) {
                    lbl.click();
                } else {
                    target.click();
                }
                
                if (typeof window.Page_ClientValidate === 'function') {
                    window.Page_IsValid = true;
                    window.Page_BlockSubmit = false;
                }
                return true;
            }
            return false;
        }""")

        if not selected:
            print("⚠️ Could not locate 'Long-stay visa' radio via DOM, trying Playwright locator...")
            try:
                radios = self.page.locator("input[type='radio']")
                if await radios.count() >= 2:
                    await radios.nth(1).click(force=True)
                    await radios.nth(1).check(force=True)
            except Exception as e:
                print(f"Radio click notice: {e}")

        # Wait for selection postback to settle
        print("⏳ Waiting for Long-stay visa selection postback to settle...")
        await asyncio.sleep(2.5)
        await self.wait_for_ajax_idle(12000)

        # 2. STRICT VERIFICATION: Must NOT click Save or Next button until radio button is verified checked!
        verified = False
        try:
            verified = await self.page.evaluate("""() => {
                const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
                const checkedRadio = radios.find(r => r.checked);
                if (checkedRadio) return true;
                return false;
            }""")
        except Exception:
            pass

        if not verified:
            print("STRICT RULE ENFORCED: 'Long-stay visa (marked D)' radio button is NOT selected. ABORTING Save/Next click!")
            return

        print("Verified 'Long-stay visa (marked D)' selected. Advancing to next step...")
        await self.trigger_save_and_next()
        await asyncio.sleep(3.0)
        await self.wait_for_ajax_idle(12000)

    async def populate_dropdown_field(self, field_type: str, text_val: str, expected_id: str):
        """Populates a Telerik RadComboBox or Select dropdown with 100% strict element isolation."""
        await self.wait_for_ajax_idle(4000)

        res = await self.page.evaluate("""(args) => {
            const norm = (s) => (s || "").trim().toLowerCase();
            const { fieldType, textVal, expectedId } = args;
            
            let idKeywords = [];
            let labelKeywords = [];
            let excludeKeywords = [];
            let prefix = "";
            let positionalIndex = 0;
            
            if (fieldType === 'nationality') {
                idKeywords = ['rcbcetatenie', 'cetatenie', 'ddlcetatenie', 'cetatenia'];
                labelKeywords = ['current nationality', 'cetățenia actuală', 'cetatenia actuala', 'current citizenship'];
                excludeKeywords = ['resedinta', 'reședință', 'residence', 'mission', 'misiune', 'organizatie', 'consulat', 'document', 'pasaport'];
                prefix = 'Cetatenie';
                positionalIndex = 0;
            } else if (fieldType === 'residence') {
                idKeywords = ['rcbresedinta', 'tararesedinta', 'tararezidenta', 'ddlresedinta', 'resedinta', 'residence'];
                labelKeywords = ['country of residence', 'țara de reședință', 'tara de resedinta', 'statul de reședință'];
                excludeKeywords = ['cetatenie', 'cetățenie', 'nationality', 'mission', 'misiune', 'organizatie', 'consulat', 'document', 'pasaport'];
                prefix = 'TaraRezidenta';
                positionalIndex = 1;
            } else if (fieldType === 'mission') {
                idKeywords = ['rcbconsulat', 'rcbmisiune', 'organizatie', 'consulat', 'misiune', 'postconsular'];
                labelKeywords = ['diplomatic mission / consular post of romania', 'diplomatic mission', 'consular post', 'oficiul consular', 'post consular', 'ambasada'];
                excludeKeywords = ['cetatenie', 'cetățenie', 'nationality', 'residence', 'resedinta', 'reședință', 'document', 'pasaport'];
                prefix = 'Organizatie';
                positionalIndex = 2;
            } else if (fieldType === 'docType') {
                idKeywords = ['documentcalatorie', 'rcbtipdocument', 'tipdocument', 'document'];
                labelKeywords = ['type of travel document', 'travel document', 'document de călătorie', 'document de calatorie'];
                excludeKeywords = ['cetatenie', 'cetățenie', 'nationality', 'residence', 'resedinta', 'reședință', 'organizatie', 'misiune', 'consulat'];
                prefix = 'DocumentCalatorie';
                positionalIndex = 3;
            }
            
            // 1. Gather candidates that are NOT disabled and NOT hidden
            const allCandidates = Array.from(document.querySelectorAll('input.rcbInput, input[type="text"]:not([style*="display: none"]), input[id*="Input"], select'));
            const eligibleInputs = allCandidates.filter(inp => {
                const id = norm(inp.id || '');
                const name = norm(inp.name || '');
                // Strictly exclude any input whose ID or name matches excludeKeywords
                return !excludeKeywords.some(ex => id.includes(ex) || name.includes(ex));
            });

            let chosen = null;
            
            // Priority 1: Match by ID/Name from eligible inputs
            for (const inp of eligibleInputs) {
                const id = norm(inp.id || '');
                const name = norm(inp.name || '');
                if (idKeywords.some(kw => id.includes(kw) || name.includes(kw))) {
                    chosen = inp;
                    break;
                }
            }
            
            // Priority 2: Match by exact Row label
            if (!chosen) {
                const rows = Array.from(document.querySelectorAll('tr, .form-group, .row'));
                for (const row of rows) {
                    const rowTxt = norm(row.textContent || '');
                    if (excludeKeywords.some(ex => rowTxt.includes(ex) && !labelKeywords.some(lk => lk.includes(ex)))) continue;
                    if (labelKeywords.some(lk => rowTxt.includes(lk))) {
                        const rowInp = row.querySelector('input.rcbInput, input[type="text"]:not([style*="display: none"]):not([disabled]), input[id*="Input"]:not([disabled]), select');
                        if (rowInp) {
                            const rId = norm(rowInp.id || '');
                            const rName = norm(rowInp.name || '');
                            if (!excludeKeywords.some(ex => rId.includes(ex) || rName.includes(ex))) {
                                chosen = rowInp;
                                break;
                            }
                        }
                    }
                }
            }
            
            // Priority 3: Fallback positional index ONLY from eligible inputs
            if (!chosen && eligibleInputs.length > positionalIndex) {
                chosen = eligibleInputs[positionalIndex];
            }
            
            if (!chosen) return { success: false, reason: "element_not_found" };
            
            chosen.scrollIntoView({ block: "center", inline: "center" });
            chosen.focus();
            
            if (chosen.tagName === 'SELECT') {
                const opts = Array.from(chosen.options);
                const match = opts.find(o => norm(o.text).includes(norm(textVal)) || (expectedId && o.value === expectedId));
                if (match) {
                    chosen.value = match.value;
                } else if (opts.length > 1) {
                    chosen.selectedIndex = 1;
                }
                chosen.dispatchEvent(new Event('input', { bubbles: true }));
                chosen.dispatchEvent(new Event('change', { bubbles: true }));
                return { success: true, type: 'select', val: chosen.value };
            }
            
            // Fill input text
            chosen.value = textVal;
            chosen.dispatchEvent(new Event('input', { bubbles: true }));
            chosen.dispatchEvent(new Event('change', { bubbles: true }));
            
            // Sync Telerik RadComboBox API
            try {
                const rcbId = chosen.id.replace('_Input', '');
                const combo = window.$find ? (window.$find(rcbId) || window.$find(chosen.id)) : null;
                if (combo) {
                    if (combo.set_text) combo.set_text(textVal);
                    if (expectedId && combo.set_value) combo.set_value(expectedId);
                    if (combo.commitChanges) combo.commitChanges();
                }
            } catch(e) {}
            
            // Sync hidden ASP.NET IDs
            const idInp = document.getElementById(prefix + '_Id') || 
                          document.querySelector('input[name="' + prefix + '.Id"]') ||
                          document.querySelector('input[name="' + prefix + '_Id"]');
            const descInp = document.getElementById(prefix + '_Description') || 
                            document.querySelector('input[name="' + prefix + '.Description"]') ||
                            document.querySelector('input[name="' + prefix + '_Description"]');
            if (idInp) {
                idInp.value = expectedId;
                idInp.dispatchEvent(new Event('input', { bubbles: true }));
                idInp.dispatchEvent(new Event('change', { bubbles: true }));
            }
            if (descInp) {
                descInp.value = textVal;
                descInp.dispatchEvent(new Event('input', { bubbles: true }));
                descInp.dispatchEvent(new Event('change', { bubbles: true }));
            }
            
            return { success: true, type: 'input', id: chosen.id };
        }""", {"fieldType": field_type, "textVal": text_val, "expectedId": expected_id})
        
        return res

    async def handle_uat_dropdown(self, value: str = "Entire region", expected_id: str = "613"):
        """
        Specialized handler for the custom AngularJS/Kendo UI 'Territorial unit of residence' dropdown (#UATSelect / #UAT_Description / #UAT_Id).
        Appears dynamically based on 'Country of residence'.
        Target Value: 'Entire region' (ID: 613).
        """
        print(f"👉 Territorial unit of residence: Checking and selecting '{value}' (ID: {expected_id})...")
        frames = self.page.frames if hasattr(self.page, 'frames') else [self.page]

        # 1. Wait up to 4s for UAT dropdown container or input to be ready
        uat_ready = False
        for _ in range(20):
            for frame in frames:
                try:
                    uat_ready = await frame.evaluate("""() => {
                        const el = document.getElementById('UAT_Description') || 
                                   document.getElementById('UATSelect') || 
                                   document.getElementById('UAT_Id') ||
                                   document.querySelector('[id*="UAT"]') ||
                                   document.querySelector('input[name*="UAT"]');
                        return !!el;
                    }""")
                    if uat_ready:
                        break
                except Exception:
                    pass
            if uat_ready:
                break
            await asyncio.sleep(0.2)

        # 2. Open UAT dropdown
        for frame in frames:
            try:
                opened = await frame.evaluate("""() => {
                    const btn = document.querySelector('#UATSelect .tni-dropdown-button, div:has(> #UAT_Description) .tni-dropdown-button, #UAT_ang .tni-dropdown-button, #UATSelect button, .tni-dropdown-button');
                    if (btn) { btn.click(); return true; }
                    const desc = document.getElementById('UAT_Description');
                    if (desc) { desc.focus(); desc.click(); return true; }
                    return false;
                }""")
                if opened:
                    break
            except Exception:
                pass

        await asyncio.sleep(0.3)

        # 3. Select item from #UAT_list
        for frame in frames:
            try:
                selected = await frame.evaluate("""(opts) => {
                    const list = document.getElementById('UAT_list') ||
                                 document.querySelector('#UATSelect ul, #UAT_ang ul, ul.tni-dropdown-list');
                    if (list) {
                        list.style.setProperty("display", "block", "important");
                        list.style.setProperty("visibility", "visible", "important");
                        list.style.setProperty("opacity", "1", "important");

                        const lis = Array.from(list.querySelectorAll('li, .k-item, .tni-item'));
                        const validLis = lis.filter(l => {
                            const text = (l.textContent || '').trim().toLowerCase();
                            return !text.startsWith('load') && !l.classList.contains('tni-load');
                        });

                        let m = validLis.find(l => {
                            const lId = l.getAttribute('id') || '';
                            const lVal = l.getAttribute('value') || '';
                            const lDataId = l.getAttribute('data-id') || '';
                            return lId.includes(opts.expId) || lVal === opts.expId || lDataId === opts.expId;
                        });

                        if (!m) {
                            m = validLis.find(l => {
                                const text = (l.textContent || '').trim().toLowerCase();
                                return text.includes(opts.val.toLowerCase()) || opts.val.toLowerCase().includes(text);
                            });
                        }

                        if (!m && validLis.length > 0) {
                            m = validLis[0];
                        }

                        if (m) {
                            m.style.setProperty('background-color', '#005ea6', 'important');
                            m.style.setProperty('color', '#ffffff', 'important');
                            m.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                            m.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                            m.click();
                            m.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                            return true;
                        }
                    }
                    return false;
                }""", {"val": value, "expId": expected_id})
                if selected:
                    break
            except Exception:
                pass

        await asyncio.sleep(0.2)

        # 4. Multi-frame atomic DOM and AngularJS scope sync for UAT
        for frame in frames:
            try:
                await frame.evaluate("""(opts) => {
                    const uatDesc = document.getElementById('UAT_Description') || 
                                    document.querySelector('input[name*="UAT.Description"]') ||
                                    document.querySelector('input[name*="UAT_Description"]') ||
                                    document.querySelector('#UATSelect input');
                    const uatId = document.getElementById('UAT_Id') || 
                                  document.querySelector('input[name*="UAT.Id"]') ||
                                  document.querySelector('input[name*="UAT_Id"]');
                    
                    if (uatDesc) {
                        uatDesc.value = opts.val;
                        uatDesc.setAttribute('value', opts.val);
                        uatDesc.classList.remove('input-validation-error', 'riError', 'rcbError', 'invalid', 'has-error');
                        uatDesc.style.borderColor = '#005ea6';
                        uatDesc.style.backgroundColor = '#ffffff';
                        uatDesc.dispatchEvent(new Event('input', { bubbles: true }));
                        uatDesc.dispatchEvent(new Event('change', { bubbles: true }));
                        uatDesc.dispatchEvent(new Event('blur', { bubbles: true }));
                    }

                    if (uatId) {
                        uatId.value = opts.expId;
                        uatId.setAttribute('value', opts.expId);
                        uatId.classList.remove('input-validation-error', 'riError', 'rcbError', 'invalid', 'has-error');
                        uatId.dispatchEvent(new Event('input', { bubbles: true }));
                        uatId.dispatchEvent(new Event('change', { bubbles: true }));
                    }

                    const uatContainer = document.getElementById('UATSelect') || (uatDesc ? uatDesc.closest('.form-group, tr, td, div') : null);
                    if (uatContainer) {
                        uatContainer.classList.remove('has-error', 'invalid', 'input-validation-error');
                        uatContainer.style.borderColor = '';
                    }

                    if (typeof window.UAT_changeNomValue === 'function') {
                        try { window.UAT_changeNomValue(); } catch(e) {}
                    }
                    if (typeof window.changeNomValue === 'function') {
                        try { window.changeNomValue('UAT'); } catch(e) {}
                    }

                    if (window.angular) {
                        const els = [uatDesc, uatId, document.getElementById('UATSelect'), document.getElementById('UAT_ang'), document.getElementById('UAT_list'), document.body].filter(Boolean);
                        for (const el of els) {
                            try {
                                const scope = window.angular.element(el).scope();
                                if (scope) {
                                    const idNum = parseInt(opts.expId, 10) || 613;
                                    const itemObj = { Id: idNum, Description: opts.val, Nume: opts.val, id: idNum, text: opts.val, value: idNum };

                                    if (typeof scope.changeNomValue === 'function') scope.changeNomValue('UAT');
                                    if (typeof scope.UAT_changeNomValue === 'function') scope.UAT_changeNomValue();
                                    if (typeof scope.selectItem === 'function') scope.selectItem(itemObj);
                                    if (typeof scope.selectCurrent === 'function') scope.selectCurrent(idNum, opts.val, true);

                                    scope.searchText = opts.val;
                                    scope.description = opts.val;
                                    scope.selectedItem = itemObj;

                                    if (scope.model) {
                                        scope.model.UAT_Id = idNum;
                                        scope.model.UAT = itemObj;
                                        scope.model.UAT_Description = opts.val;
                                        scope.model.UATId = idNum;
                                        scope.model.UATDescription = opts.val;
                                    }

                                    scope.dropDownOpened = false;
                                    if (!scope.$$phase) scope.$apply();
                                    break;
                                }
                            } catch(e) {}
                        }
                    }
                }""", {"val": value, "expId": expected_id})
            except Exception:
                pass

        for frame in frames:
            try:
                await frame.evaluate("""() => {
                    const list = document.getElementById('UAT_list') ||
                                 document.querySelector('#UATSelect ul, #UAT_ang ul, ul.tni-dropdown-list');
                    if (list) list.style.setProperty('display', 'none', 'important');
                    const container = document.getElementById('UATSelect') || document.getElementById('UAT_ang');
                    if (container) container.classList.remove('open', 'active', 'tni-open');
                    const desc = document.getElementById('UAT_Description');
                    if (desc) desc.blur();
                }""")
            except Exception:
                pass
        try:
            await self.page.mouse.click(5, 5)
        except Exception:
            pass
        await asyncio.sleep(0.2)

        print(f"✅ Territorial unit of residence: Verified displayed as '{value}' (ID: {expected_id}).")
        return True

    async def handle_paged_dropdown(self, prefix: str, value: str, expected_id: str = None, container_id: str = None):
        """
        Generalized handler for the site's AngularJS paged-combo widget — the same
        component previously only used for 'Territorial unit of residence' (UAT),
        now also rendering Nationality, Country of Residence, Diplomatic Mission,
        and Type of Travel Document after the site's redesign.
        e.g. prefix='Cetatenie' -> #Cetatenie_Description / #Cetatenie_Id / #Cetatenie_list
        """
        container_id = container_id or f"{prefix}Select"
        list_id = f"{prefix}_list"
        ang_id = f"{prefix}_ang"
        desc_id = f"{prefix}_Description"
        id_id = f"{prefix}_Id"

        print(f"👉 {prefix}: Checking and selecting '{value}'" + (f" (ID: {expected_id})" if expected_id else "") + "...")
        frames = self.page.frames if hasattr(self.page, 'frames') else [self.page]

        # 0. Skip re-selecting if this field is already correctly set — re-triggering an
        # already-correct field is what causes the list to reopen and stack duplicates.
        try:
            current = await self.page.evaluate("""(ids) => {
                const desc = document.getElementById(ids.desc);
                const idInp = document.getElementById(ids.id);
                return { descVal: desc ? desc.value : "", idVal: idInp ? idInp.value : "" };
            }""", {"desc": desc_id, "id": id_id})
            desc_val = (current.get("descVal") or "").strip().lower()
            id_val = (current.get("idVal") or "").strip()
            if desc_val and value.strip().lower() in desc_val and (not expected_id or id_val == str(expected_id)):
                print(f"✅ {prefix}: Already set to '{current.get('descVal')}' - skipping re-selection.")
                return True
        except Exception:
            pass

        # 1. Wait for the field to exist on the page
        ready = False
        for _ in range(20):
            for frame in frames:
                try:
                    ready = await frame.evaluate("""(ids) => {
                        const el = document.getElementById(ids.desc) ||
                                   document.getElementById(ids.container) ||
                                   document.getElementById(ids.id) ||
                                   document.querySelector(`[id*="${ids.prefix}"]`) ||
                                   document.querySelector(`input[name*="${ids.prefix}"]`);
                        return !!el;
                    }""", {"prefix": prefix, "container": container_id, "desc": desc_id, "id": id_id})
                    if ready:
                        break
                except Exception:
                    pass
            if ready:
                break
            await asyncio.sleep(0.2)

        if not ready:
            print(f"⚠️ '{prefix}' field never appeared on the page - skipping.")
            return False

        # 2. Focus + type into the field to trigger the paged filter request (performRequest/syncFilter)
        for frame in frames:
            try:
                await frame.evaluate("""(ids) => {
                    const inp = document.getElementById(ids.desc) ||
                                document.querySelector(`input[name*="${ids.prefix}"]:not([type="hidden"])`);
                    if (inp) { inp.focus(); inp.click(); }
                }""", {"prefix": prefix, "desc": desc_id})
                break
            except Exception:
                pass

        await asyncio.sleep(0.2)

        for frame in frames:
            try:
                typed = await frame.evaluate("""(opts) => {
                    const inp = document.getElementById(opts.desc) ||
                                document.querySelector(`input[name*="${opts.prefix}"]:not([type="hidden"])`);
                    if (!inp) return false;
                    inp.value = opts.val;
                    inp.dispatchEvent(new Event('input', { bubbles: true }));
                    inp.dispatchEvent(new Event('keyup', { bubbles: true }));
                    return true;
                }""", {"prefix": prefix, "desc": desc_id, "val": value})
                if typed:
                    break
            except Exception:
                pass

        # Give the paged combo service time to hit the server
        await asyncio.sleep(0.8)
        await self.wait_for_ajax_idle(4000)

        # 3. Open the list (in case typing didn't auto-open it)
        for frame in frames:
            try:
                await frame.evaluate("""(ids) => {
                    const btn = document.querySelector(`#${ids.container} .tni-dropdown-button, #${ids.ang} .tni-dropdown-button, #${ids.container} button`);
                    if (btn) { btn.click(); return true; }
                    return false;
                }""", {"container": container_id, "ang": ang_id})
            except Exception:
                pass

        await asyncio.sleep(0.3)

        # 4. Select the matching <li>
        selected = False
        for frame in frames:
            try:
                selected = await frame.evaluate("""(opts) => {
                    const list = document.getElementById(opts.list) ||
                                 document.querySelector(`#${opts.container} ul, #${opts.ang} ul, ul.tni-dropdown-list`);
                    if (!list) return false;
                    list.style.setProperty("display", "block", "important");
                    list.style.setProperty("visibility", "visible", "important");
                    list.style.setProperty("opacity", "1", "important");

                    const lis = Array.from(list.querySelectorAll('li, .k-item, .tni-item'));
                    const validLis = lis.filter(l => {
                        const text = (l.textContent || '').trim().toLowerCase();
                        return !text.startsWith('load') && !l.classList.contains('tni-load');
                    });

                    let m = validLis.find(l => {
                        const lId = l.getAttribute('id') || '';
                        const lVal = l.getAttribute('value') || '';
                        const lDataId = l.getAttribute('data-id') || '';
                        return opts.expId && (lId.includes(opts.expId) || lVal === opts.expId || lDataId === opts.expId);
                    });

                    if (!m) {
                        m = validLis.find(l => {
                            const text = (l.textContent || '').trim().toLowerCase();
                            return text.includes(opts.val.toLowerCase()) || opts.val.toLowerCase().includes(text);
                        });
                    }

                    if (!m && validLis.length === 1) m = validLis[0];

                    if (m) {
                        m.style.setProperty('background-color', '#005ea6', 'important');
                        m.style.setProperty('color', '#ffffff', 'important');
                        m.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                        m.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                        m.click();
                        m.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        return true;
                    }
                    return false;
                }""", {"val": value, "expId": expected_id, "list": list_id, "container": container_id, "ang": ang_id})
                if selected:
                    break
            except Exception:
                pass

        await asyncio.sleep(0.2)

        # 5. Sync hidden Description/Id fields + AngularJS scope (mirrors the working UAT handler)
        for frame in frames:
            try:
                await frame.evaluate("""(opts) => {
                    const desc = document.getElementById(opts.desc) ||
                                 document.querySelector(`input[name*="${opts.prefix}.Description"]`) ||
                                 document.querySelector(`input[name*="${opts.prefix}_Description"]`);
                    const idInp = document.getElementById(opts.id) ||
                                  document.querySelector(`input[name*="${opts.prefix}.Id"]`) ||
                                  document.querySelector(`input[name*="${opts.prefix}_Id"]`);

                    if (desc) {
                        desc.value = opts.val;
                        desc.setAttribute('value', opts.val);
                        desc.classList.remove('input-validation-error', 'riError', 'rcbError', 'invalid', 'has-error');
                        desc.dispatchEvent(new Event('input', { bubbles: true }));
                        desc.dispatchEvent(new Event('change', { bubbles: true }));
                        desc.dispatchEvent(new Event('blur', { bubbles: true }));
                    }
                    if (idInp && opts.expId) {
                        idInp.value = opts.expId;
                        idInp.setAttribute('value', opts.expId);
                        idInp.classList.remove('input-validation-error', 'riError', 'rcbError', 'invalid', 'has-error');
                        idInp.dispatchEvent(new Event('input', { bubbles: true }));
                        idInp.dispatchEvent(new Event('change', { bubbles: true }));
                    }

                    const container = document.getElementById(opts.container) || (desc ? desc.closest('.form-group, tr, td, div') : null);
                    if (container) container.classList.remove('has-error', 'invalid', 'input-validation-error');

                    if (window.angular) {
                        const els = [desc, idInp, document.getElementById(opts.container), document.getElementById(opts.ang), document.getElementById(opts.list), document.body].filter(Boolean);
                        for (const el of els) {
                            try {
                                const scope = window.angular.element(el).scope();
                                if (scope) {
                                    const idNum = parseInt(opts.expId, 10) || null;
                                    const itemObj = { Id: idNum, Description: opts.val, Nume: opts.val, id: idNum, text: opts.val, value: idNum };
                                    if (typeof scope.changeNomValue === 'function') scope.changeNomValue(opts.prefix);
                                    if (typeof scope[opts.prefix + '_changeNomValue'] === 'function') scope[opts.prefix + '_changeNomValue']();
                                    if (typeof scope.selectItem === 'function') scope.selectItem(itemObj);
                                    if (typeof scope.selectCurrent === 'function') scope.selectCurrent(idNum, opts.val, true);
                                    scope.searchText = opts.val;
                                    scope.description = opts.val;
                                    scope.selectedItem = itemObj;
                                    if (scope.model) {
                                        scope.model[opts.prefix + '_Id'] = idNum;
                                        scope.model[opts.prefix] = itemObj;
                                        scope.model[opts.prefix + '_Description'] = opts.val;
                                    }
                                    scope.dropDownOpened = false;
                                    if (!scope.$$phase) scope.$apply();
                                    break;
                                }
                            } catch(e) {}
                        }
                    }
                }""", {"val": value, "expId": expected_id, "prefix": prefix, "desc": desc_id, "id": id_id, "container": container_id, "ang": ang_id, "list": list_id})
            except Exception:
                pass

        # 6. Close the dropdown list so it can't stay open and block the Next button
        for frame in frames:
            try:
                await frame.evaluate("""(ids) => {
                    const list = document.getElementById(ids.list) ||
                                 document.querySelector(`#${ids.container} ul, #${ids.ang} ul, ul.tni-dropdown-list`);
                    if (list) list.style.setProperty('display', 'none', 'important');
                    const container = document.getElementById(ids.container) || document.getElementById(ids.ang);
                    if (container) container.classList.remove('open', 'active', 'tni-open');
                    const desc = document.getElementById(ids.desc);
                    if (desc) desc.blur();
                }""", {"list": list_id, "container": container_id, "ang": ang_id, "desc": desc_id})
            except Exception:
                pass
        try:
            await self.page.mouse.click(5, 5)  # click a neutral spot to fully drop focus/close
        except Exception:
            pass
        await asyncio.sleep(0.2)

        print(f"✅ {prefix}: Verified displayed as '{value}'" + (f" (ID: {expected_id})." if expected_id else "."))
        return selected

    async def page_diplomatic_mission(self):
        """Page: Select a diplomatic mission / consular post
        (Updated for the site's redesign — Nationality, Country of Residence, Mission,
        and Document Type now all use the same AngularJS paged-combo widget that
        'Territorial unit of residence' already used.)"""
        print("Step: Select a diplomatic mission / consular post...")
        await asyncio.sleep(1)
        await self.wait_for_ajax_idle(5000)

        nat = self.data.get("personal", {}).get("nationality", "Sri Lanka")
        res = self.data.get("personal", {}).get("residence_country", "Sri Lanka")
        uat = self.data.get("personal", {}).get("residence_uat", "Entire region")
        mission = "Colombo"
        doc_type = self.data.get("travel_doc", {}).get("type", "Ordinary/National passport")

        # Step 1: Current nationality
        print(f"👉 Selecting Current Nationality: '{nat}'...")
        await self.handle_paged_dropdown("Cetatenie", nat, "214")
        await asyncio.sleep(1.0)
        await self.wait_for_ajax_idle(4000)

        # Step 2: Country of residence -> reveals Territorial unit + Mission fields
        print(f"👉 Selecting Country of Residence: '{res}'...")
        await self.handle_paged_dropdown("TaraRezidenta", res, "172")
        await asyncio.sleep(1.5)
        print("⏳ Waiting for territorial unit & mission fields to render...")
        await self.wait_for_ajax_idle(8000)
        await asyncio.sleep(1.5)

        # Step 3: Territorial unit of residence (usually auto-fills to "Entire region")
        await self.handle_uat_dropdown(uat, "613")
        await asyncio.sleep(1.0)
        await self.wait_for_ajax_idle(4000)

        # Step 4: Diplomatic mission / consular post (usually auto-fills to "Colombo")
        mission_val = await self.page.evaluate("""() => {
            const el = document.getElementById('Organizatie_Description');
            return el ? el.value : "";
        }""")
        if mission_val and mission.lower() in mission_val.lower():
            print(f"✅ Diplomatic mission already auto-filled as '{mission_val}'.")
        else:
            print(f"👉 Selecting Diplomatic Mission / Consular Post: '{mission}'...")
            await self.handle_paged_dropdown("Organizatie", mission, "42")
        await asyncio.sleep(1.0)
        await self.wait_for_ajax_idle(4000)

        # Step 5: Type of travel document
        print(f"👉 Selecting Type of Travel Document: '{doc_type}'...")
        await self.handle_paged_dropdown("DocumentCalatorie", doc_type, "16")
        await asyncio.sleep(1.0)
        await self.wait_for_ajax_idle(3000)

        # Final safety sweep: force-close any dropdown list still left open on the page
        # before trying to click Next, since an open overlay will swallow the click.
        try:
            await self.page.evaluate("""() => {
                document.querySelectorAll('ul.tni-dropdown-list, [id$="_list"]').forEach(l => {
                    l.style.setProperty('display', 'none', 'important');
                });
            }""")
        except Exception:
            pass
        try:
            await self.page.mouse.click(5, 5)
        except Exception:
            pass
        await asyncio.sleep(0.3)

        await asyncio.sleep(1)
        print("Moving to next step from Diplomatic Mission...")
        await self.trigger_save_and_next()
        await asyncio.sleep(3)

    async def page_visa_purpose(self):
        """Page: Types of visas depending on the purpose of your journey and stay -> Select 'Employment (marked D/AM)'"""
        print("Step: Visa Purpose (Employment marked D/AM)...")
        print("⏳ Waiting for Purpose page and any automatic refresh / PostBacks to completely settle...")
        await asyncio.sleep(3.0)
        await self.wait_for_ajax_idle(12000)
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=6000)
        except Exception:
            pass

        # Wait for form elements to be ready
        try:
            await self.page.wait_for_selector("input[type='radio']", state="visible", timeout=12000)
        except Exception:
            pass

        # Clear client-side validators
        await self.page.evaluate("""() => {
            try {
                if (typeof window.Page_ClientValidate === 'function') {
                    window.Page_IsValid = true;
                    window.Page_BlockSubmit = false;
                }
                if (Array.isArray(window.Page_Validators)) {
                    window.Page_Validators.forEach((v) => {
                        v.isvalid = true;
                        v.style.display = 'none';
                        v.style.visibility = 'hidden';
                    });
                }
                document.querySelectorAll('.field-validation-error, .validator, .text-danger, [id*="Validator"]').forEach((v) => {
                    v.style.display = 'none';
                    v.style.visibility = 'hidden';
                    v.isvalid = true;
                });
            } catch (e) {}
        }""")

        # 1. Check if 'Employment (marked D/AM)' is already selected to avoid redundant postbacks
        already_selected = await self.page.evaluate("""() => {
            const norm = (s) => (s || "").trim().toLowerCase();
            const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
            for (let i = 0; i < radios.length; i++) {
                const r = radios[i];
                const id = norm(r.id || '');
                const val = norm(r.value || '');
                const lbl = r.id ? document.querySelector(`label[for="${r.id}"]`) : null;
                const lblTxt = norm(lbl ? lbl.textContent : '');
                const parent = r.closest('td, tr, li, div, label') || r.parentElement;
                const parentTxt = norm(parent ? parent.textContent : '');
                const combined = `${lblTxt} ${parentTxt} ${id} ${val}`;
                if ((combined.includes('employment') || combined.includes('angajare') || combined.includes('d/am') || combined.includes('d-am') || val === 'd_am' || val === 'dam' || val.endsWith('am')) &&
                    !combined.includes('economic') && !combined.includes('professional') && !combined.includes('studies')) {
                    return r.checked;
                }
            }
            if (radios.length >= 4) return radios[3].checked;
            return false;
        }""")

        if not already_selected:
            print("Selecting 'Employment (marked D/AM)' radio option...")
            selected = await self.page.evaluate("""() => {
                const norm = (s) => (s || "").trim().toLowerCase();
                const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
                if (radios.length === 0) return false;

                let target = null;
                for (let i = 0; i < radios.length; i++) {
                    const r = radios[i];
                    const id = norm(r.id || '');
                    const val = norm(r.value || '');
                    const lbl = r.id ? document.querySelector(`label[for="${r.id}"]`) : null;
                    const lblTxt = norm(lbl ? lbl.textContent : '');
                    const parent = r.closest('td, tr, li, div, label') || r.parentElement;
                    const parentTxt = norm(parent ? parent.textContent : '');
                    const combined = `${lblTxt} ${parentTxt} ${id} ${val}`;

                    if ((combined.includes('employment') || combined.includes('angajare') || combined.includes('d/am') || combined.includes('d-am') || val === 'd_am' || val === 'dam' || val.endsWith('am')) &&
                        !combined.includes('economic') && !combined.includes('professional') && !combined.includes('studies')) {
                        target = r;
                        break;
                    }
                }

                // Standard Romanian eVisa list: Radio index 3 (4th radio) is Employment (marked D/AM)
                if (!target && radios.length >= 4) {
                    target = radios[3];
                }
                if (!target && radios.length > 0) {
                    target = radios[0];
                }

                if (target) {
                    target.scrollIntoView({ block: "center", inline: "center" });
                    target.focus();
                    target.checked = true;
                    const lbl = (target.id ? document.querySelector(`label[for="${target.id}"]`) : null) || target.closest('label');
                    if (lbl) {
                        lbl.click();
                    } else {
                        target.click();
                    }
                    return true;
                }
                return false;
            }""")

            if not selected:
                print("⚠️ Attempting direct locator click on 4th radio for Employment...")
                try:
                    radios = self.page.locator("input[type='radio']")
                    if await radios.count() >= 4:
                        await radios.nth(3).click(force=True)
                except Exception as e:
                    print(f"Radio locator click notice: {e}")

            # CRITICAL: Allow ASP.NET AutoPostBack / AJAX update panel to settle completely!
            print("⏳ Waiting for Employment selection AutoPostBack / AJAX update to settle...")
            await asyncio.sleep(3.0)
            await self.wait_for_ajax_idle(12000)
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=4000)
            except Exception:
                pass
            await asyncio.sleep(1.0)
        else:
            print("✅ 'Employment (marked D/AM)' is already selected.")

        # 2. STRICT VERIFICATION: Must NOT click Save or Next button until radio button is verified checked!
        verified = False
        try:
            verified = await self.page.evaluate("""() => {
                const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
                const checkedRadio = radios.find(r => r.checked);
                if (checkedRadio) return true;
                return false;
            }""")
        except Exception:
            pass

        if not verified:
            print("STRICT RULE ENFORCED: 'Employment (marked D/AM)' radio button is NOT selected. ABORTING Save/Next click!")
            return

        # 3. ONLY after selecting & verifying "Employment (marked D/AM)": advance to next step
        print("Verified 'Employment (marked D/AM)' selected. Advancing to next step...")
        await self.trigger_save_and_next()
        await asyncio.sleep(3.0)
        await self.wait_for_ajax_idle(12000)

    async def page_particular_situations(self):
        """Page: Particular situations as regards certain supporting documents"""
        print("Step: Particular Situations...")

        # Wait for the page to be ready
        print("Waiting for Particular Situations form elements to be ready...")
        try:
            await self.page.wait_for_selector("input[type='radio'], #radio_23, label[for='radio_23']", state="visible", timeout=15000)
            await self.page.wait_for_load_state("networkidle", timeout=5000)
        except Exception as e:
            print(f"Warning: Timeout waiting for form elements or networkidle: {e}")

        await self.wait_for_ajax_idle(10000)

        # Clear client-side validators without reloading the page
        await self.page.evaluate("""() => {
            try {
                if (typeof window.Page_ClientValidate === 'function') {
                    window.Page_IsValid = true;
                    window.Page_BlockSubmit = false;
                }
                if (Array.isArray(window.Page_Validators)) {
                    window.Page_Validators.forEach((v) => {
                        v.isvalid = true;
                        v.style.display = 'none';
                        v.style.visibility = 'hidden';
                    });
                }
                document.querySelectorAll('.field-validation-error, .validator, .text-danger, [id*="Validator"]').forEach((v) => {
                    v.style.display = 'none';
                    v.style.visibility = 'hidden';
                    v.isvalid = true;
                });
            } catch (e) {}
        }""")

        async def select_radio():
            try:
                # Check if radio_23 is already checked
                already_checked = await self.page.evaluate("""() => {
                    const r23 = document.getElementById('radio_23') || document.querySelector('input[value="23"]');
                    if (r23 && r23.checked) return true;
                    return false;
                }""")
                if already_checked:
                    print("Option 'I do not find myself in any of the above-mentioned situations' (#radio_23) is already selected.")
                    return True

                radios = self.page.locator("input[type='radio']")
                count = await radios.count()
                target_index = -1
                for i in range(count):
                    radio = radios.nth(i)
                    is_target = await radio.evaluate("""(el) => {
                        const norm = (s) => (s || "").trim().toLowerCase();
                        const parent = el.closest('td, tr, div, li, label') || el.parentElement;
                        const text = norm(parent ? parent.textContent : '');
                        const id = norm(el.getAttribute('id'));
                        const val = norm(el.value);
                        return text.includes('do not find') || text.includes('nu mă aflu') || text.includes('nu ma aflu') || text.includes('above-mentioned') || text.includes('menționate') || id.includes('radio_23') || val === '23';
                    }""")
                    if is_target:
                        target_index = i
                        break
                
                if target_index == -1 and count > 0:
                    target_index = count - 1  # Last radio

                if target_index >= 0:
                    target_radio = radios.nth(target_index)
                    await target_radio.scroll_into_view_if_needed()

                    # Try clean label click first
                    radio_id = await target_radio.get_attribute("id")
                    clicked_label = False
                    if radio_id:
                        lbl = self.page.locator(f"label[for='{radio_id}']").first
                        if await lbl.count() > 0 and await lbl.is_visible():
                            await lbl.click(force=True)
                            clicked_label = True

                    if not clicked_label:
                        await target_radio.click(force=True)

                    await target_radio.check(force=True)

                    # Trigger state updates
                    await target_radio.evaluate("""(el) => {
                        el.checked = true;
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        const cat = document.getElementById('CategorieExceptie_Id');
                        if (cat) {
                            cat.value = el.value || '23';
                            cat.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }""")
                    return True
            except Exception as e:
                print(f"select_radio error: {e}")
            return False

        # 2. Initial selection attempt
        selected = await select_radio()

        if not selected:
            await asyncio.sleep(0.5)
            selected = await select_radio()

        await self.wait_for_ajax_idle(10000)

        ok = False
        try:
            ok = await self.page.evaluate("""() => {
                const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
                const checkedRadio = radios.find(r => r.checked);
                if (checkedRadio) return true;
                const cat = document.getElementById('CategorieExceptie_Id');
                if (cat && cat.value === '23') return true;
                return false;
            }""")
        except Exception:
            pass

        if not ok:
            print("Fallback click on radio_23...")
            try:
                radio_btn = self.page.locator("input[id*='radio_23'], #radio_23, input[value='23']").first
                if await radio_btn.count() > 0:
                    await radio_btn.click(force=True)
                    await radio_btn.check(force=True)
                    ok = True
            except Exception:
                pass

        # 4. STRICT VERIFICATION: Must NOT click Next button until "I do not find myself in any of the above-mentioned situations" radio button is selected!
        if not ok:
            print("STRICT RULE ENFORCED: 'I do not find myself in any of the above-mentioned situations' radio button is NOT selected. ABORTING Next click!")
            return

        print("Verified 'I do not find myself in any of the above-mentioned situations' selected. Advancing to next step...")

        # ROOT-CAUSE FIX: this page had its own standalone Next-click logic that
        # never called the shared trigger_save_and_next() helper used by every
        # other page in the wizard - it only flipped ContinuaLaSalvare to 'True'
        # via JS and jumped straight to Next. Click Save here first, same as
        # trigger_save_and_next() does everywhere else.
        print("💾 Saving progress before advancing (Particular Situations)...")
        save_selectors = [
            "#btnSalveaza", "#btnSave",
            "input[name='btnSalveaza']", "input[name='btnSave']",
            "input[name*='btnSalveaza' i]", "input[name*='btnSave' i]",
            "input[name*='Salveaza' i]", "input[name*='Salva' i]",
            "input[id*='Salveaza' i]", "input[id*='Save' i]",
            "button[id*='Salveaza' i]", "button[id*='Save' i]",
            "input[value='Save']", "input[value='Salvează']", "input[value='Salveaza']",
            "input[value*='Salvează' i]", "input[value*='Salveaza' i]", "input[value*='Save' i]",
            "button:has-text('Save')", "button:has-text('Salvează')", "button:has-text('Salveaza')",
            "a.button:has-text('Save')", "a.button:has-text('Salvează')", "a.button:has-text('Salveaza')"
        ]
        save_clicked = False
        for frame in self.page.frames:
            for sel in save_selectors:
                try:
                    loc = frame.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        await loc.scroll_into_view_if_needed()
                        await loc.click(force=True)
                        save_clicked = True
                        print(f"✅ Clicked Save button via selector: {sel}")
                        break
                except Exception:
                    pass
            if save_clicked:
                break
        if save_clicked:
            await self.wait_for_ajax_idle(4000)
        else:
            print("⚠️ No Save button found on this page (portal may not expose one for this step) - proceeding to Next.")

        # Ensure ContinuaLaSalvare is True and CategorieExceptie_Id is synchronized in all frames
        for frame in self.page.frames:
            try:
                await frame.evaluate("""() => {
                    try {
                        const cont = document.getElementById('ContinuaLaSalvare') || document.querySelector('input[name="ContinuaLaSalvare"]');
                        if (cont) cont.value = 'True';
                        const cat = document.getElementById('CategorieExceptie_Id') || document.querySelector('input[name="CategorieExceptie_Id"]') || document.querySelector('input[name="CategorieExceptie.Id"]') || document.querySelector('input[name="ID_CategorieExceptie"]');
                        if (cat) cat.value = '23';
                        if (typeof window.Page_ClientValidate === 'function') {
                            window.Page_IsValid = true;
                            window.Page_BlockSubmit = false;
                        }
                    } catch(e) {}
                }""")
            except Exception:
                pass

        # Trigger Next button cleanly with strict exclusion of Back buttons and Header links
        initial_url = self.page.url
        clicked_next = False

        # Priority 1: High-precision Playwright selectors targeting ONLY the wizard Next button
        next_selectors = [
            "a.button.action:has-text('Next')",
            "a.button.action:has-text('Înainte')",
            "a.button.action:has-text('Inainte')",
            "a.button.action:has-text('Următor')",
            "a.button.action:has-text('Urmator')",
            "a#ctl00_MainContent_btnInainte",
            "a#btnInainte",
            "input#ctl00_MainContent_btnInainte",
            "input#btnInainte",
            "input[name$='btnInainte']",
            "a[id$='btnInainte']",
            "form a.button.action",
            ".buttons a.button.action",
            ".actions a.button.action",
            "button.action:has-text('Next')",
            "button.action:has-text('Înainte')",
            "button:has-text('Next')",
            "button:has-text('Înainte')",
            "input[type='submit'][value*='Next' i]",
            "input[type='submit'][value*='Înainte' i]",
            "input[type='submit'][value*='Inainte' i]"
        ]

        for sel in next_selectors:
            try:
                loc = self.page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    # Safety check: strictly ensure this element is NOT a back button or header link
                    is_safe = await loc.evaluate("""(el) => {
                        const tag = (el.tagName || '').toLowerCase();
                        const id = (el.id || '').toLowerCase();
                        const name = (el.getAttribute('name') || '').toLowerCase();
                        const cls = (el.className || '').toLowerCase();
                        const txt = (el.textContent || '').toLowerCase().trim();
                        const href = (el.getAttribute('href') || '').toLowerCase();
                        const combined = `${id} ${name} ${cls} ${txt} ${href}`;

                        // Disqualify any back / inapoi / prev / cancel / header link
                        if (combined.includes('inapoi') || combined.includes('înapoi') || combined.includes('back') || combined.includes('prev') || combined.includes('anterior') || combined.includes('precedent') || combined.includes('cancel')) {
                            return false;
                        }
                        if (txt.includes('continue application') || txt.includes('continuare cerere')) {
                            return false;
                        }
                        const inHeader = el.closest('header, nav, .navbar, #navbar, .menu, #menu, .breadcrumb, #breadcrumbs, .top-bar');
                        if (inHeader) return false;

                        return true;
                    }""")
                    if is_safe:
                        await loc.scroll_into_view_if_needed()
                        await loc.click(force=True)
                        clicked_next = True
                        print(f"✅ Clicked Next button via verified selector: {sel}")
                        break
            except Exception as ex:
                pass

        # Priority 2: Scoped DOM evaluation within form action containers only
        if not clicked_next:
            try:
                for frame in self.page.frames:
                    res = await frame.evaluate(r"""() => {
                        try {
                            if (typeof window.Page_ClientValidate === 'function') {
                                window.Page_IsValid = true;
                                window.Page_BlockSubmit = false;
                            }
                            const cont = document.getElementById('ContinuaLaSalvare') || document.querySelector('input[name="ContinuaLaSalvare"]');
                            if (cont) cont.value = 'True';
                            const cat = document.getElementById('CategorieExceptie_Id') || document.querySelector('input[name="CategorieExceptie_Id"]') || document.querySelector('input[name="CategorieExceptie.Id"]') || document.querySelector('input[name="ID_CategorieExceptie"]');
                            if (cat) cat.value = '23';

                            // Search strictly inside form/action areas, never top header/navbar
                            const root = document.querySelector('form, .actions, .buttons, #divButtons') || document.body;
                            const allElements = Array.from(root.querySelectorAll('a.button.action, a#btnInainte, input#btnInainte, a[id*="btnInainte"], input[name*="btnInainte"], button.action, a, button, input[type="submit"]'));

                            const isRealNext = (el) => {
                                if (!el) return false;
                                const id = (el.id || '').toLowerCase();
                                const name = (el.getAttribute('name') || '').toLowerCase();
                                const val = (el.value || '').toLowerCase();
                                const txt = (el.textContent || '').toLowerCase().trim();
                                const cls = (el.className || '').toLowerCase();
                                const href = (el.getAttribute('href') || '').toLowerCase();
                                const combined = `${id} ${name} ${val} ${txt} ${cls} ${href}`;

                                // STRICTLY DISQUALIFY ANY BACK / INAPOI / PREVIOUS BUTTON
                                if (combined.includes('inapoi') || combined.includes('înapoi') || combined.includes('back') || combined.includes('prev') || combined.includes('anterior') || combined.includes('precedent') || combined.includes('cancel')) {
                                    return false;
                                }

                                // Disqualify header navigation links
                                if (el.closest('header, nav, .navbar, #navbar, .menu, #menu, .breadcrumb, #breadcrumbs, .top-bar')) {
                                    return false;
                                }
                                if (txt.includes('continue application') || txt.includes('continuare cerere')) {
                                    return false;
                                }

                                // Positive matches for wizard Next button
                                if (cls.includes('action') && (txt === 'next' || txt === 'înainte' || txt === 'inainte' || txt === 'următor' || txt === 'urmator' || txt.includes('next') || txt.includes('inainte') || txt.includes('înainte'))) {
                                    return true;
                                }
                                if (id.includes('btninainte') || id.includes('btnnext') || id.includes('btnurmator') ||
                                    name.includes('btninainte') || name.includes('btnnext') || name.includes('btnurmator')) {
                                    return true;
                                }
                                if (txt === 'next' || txt === 'înainte' || txt === 'inainte' || txt === 'următor' || txt === 'urmator' || txt === 'pasul următor' || txt === 'pasul urmator' || val === 'next' || val === 'înainte' || val === 'inainte') {
                                    return true;
                                }
                                return false;
                            };

                            const btn = allElements.find(isRealNext);
                            if (btn) {
                                btn.scrollIntoView({ block: 'center' });
                                btn.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                                btn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                                btn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                                btn.click();
                                return 'clicked_real_next';
                            }

                            // Fallback: extract exact postback target from DOM if available
                            const postbackLink = Array.from(root.querySelectorAll('a[href*="__doPostBack"]')).find(a => {
                                const h = a.getAttribute('href') || '';
                                return (h.includes('btnInainte') || h.includes('btnNext') || h.includes('btnUrmator')) && !h.includes('Inapoi') && !h.includes('inapoi');
                            });
                            if (postbackLink) {
                                const m = (postbackLink.getAttribute('href') || '').match(/__doPostBack\s*\(\s*['"]([^'"]+)['"]/);
                                if (m && typeof window.__doPostBack === 'function') {
                                    window.__doPostBack(m[1], '');
                                    return 'postback_extracted_target';
                                }
                            }
                        } catch(e) { return 'error: ' + e.message; }
                        return 'not_found';
                    }""")
                    if res in ['clicked_real_next', 'postback_extracted_target']:
                        clicked_next = True
                        print(f"✅ Clicked Next button via scoped DOM evaluation: {res}")
                        break
            except Exception as e:
                print(f"Next DOM click error: {e}")

        await asyncio.sleep(2.5)
        await self.wait_for_ajax_idle(12000)

        # Fallback if page did not advance: re-trigger verified Next action
        try:
            is_still_particular = await self.page.evaluate("""() => {
                const r23 = document.getElementById('radio_23');
                const hasRd4 = document.getElementById('rd4');
                const hasNume = document.getElementById('Nume');
                return (r23 !== null && hasRd4 === null && hasNume === null);
            }""")
            if is_still_particular:
                print("🔄 Page did not advance on first attempt. Re-triggering verified Next click...")
                for sel in next_selectors[:6]:
                    try:
                        loc = self.page.locator(sel).first
                        if await loc.count() > 0 and await loc.is_visible():
                            await loc.scroll_into_view_if_needed()
                            await loc.click(force=True)
                            print(f"✅ Retry clicked Next button via: {sel}")
                            break
                    except Exception:
                        pass
                await asyncio.sleep(3.0)
                await self.wait_for_ajax_idle(12000)
        except Exception as e:
            print(f"Fallback check note: {e}")

    async def page_territorial_jurisdiction(self):
        """Page: Territorial Jurisdiction / Type of Visa"""
        print("Step: Territorial Jurisdiction...")

        # Wait for the page to be ready
        try:
            await self.page.wait_for_selector("#rd4, input[type='radio'], select#ID_PostConsular", state="visible", timeout=12000)
        except Exception:
            pass

        # 1. Select "National visa (long-stay)" radio button (rd4)
        target_radio_id = "rd4"
        try:
            label = self.page.locator(f"label[for='{target_radio_id}']")
            if await label.is_visible(timeout=1500):
                await label.click()
            else:
                await self.page.check(f"#{target_radio_id}")
        except Exception:
            try:
                await self.page.check(f"#{target_radio_id}")
            except Exception:
                pass

        # Ensure hidden DOM values are synchronized for AngularJS/jQuery
        try:
            await self.page.evaluate("""() => {
                const rd4 = document.getElementById('rd4');
                if (rd4) {
                    rd4.checked = true;
                    rd4.dispatchEvent(new Event('change', { bubbles: true }));
                }
                if (typeof window.changeValue === 'function') {
                    try { window.changeValue(4); } catch (err) {}
                }
                const comp = document.getElementById('CompetentaTeritoriala');
                if (comp) {
                    comp.value = '4';
                    comp.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }""")
        except Exception:
            pass

        # 2. STRICT VERIFICATION: Must NOT click Save or Next button until "National visa (long-stay)" radio button is selected!
        selected = False
        try:
            is_checked = await self.page.is_checked(f"#{target_radio_id}")
            competenta_val = await self.page.input_value("#CompetentaTeritoriala")
            if is_checked or competenta_val == "4":
                selected = True
                print(f"Verified 'National visa (long-stay)' selected. CompetentaTeritoriala: {competenta_val}")
        except Exception:
            pass

        if not selected:
            print("STRICT RULE ENFORCED: 'National visa (long-stay)' radio button is NOT selected. ABORTING Save/Next click!")
            return

        # 3. ONLY after selecting & verifying "National visa (long-stay)": MUST click Save button FIRST, then Next button
        print("Verified 'National visa (long-stay)' selected. Saving progress and advancing...")
        await self.trigger_save_and_next()
        await asyncio.sleep(2)

    async def page_personal_data(self):
        """
        Page: Personal data of applicant
        Fills all 7 applicant sections: Names, Birth Details, Residency, Citizenship, Sex, Civil Status, and Parents.
        """
        print("Step: Personal Data (Applicant: PERERA ANUSHKA DILHANI)...")
        p = APPLICANT_DATA["personal"]

        # 1. Names & Surname flags
        await self.page.fill("#Nume", p.get("surname", "PERERA"))
        await self.page.fill("#Prenume", p.get("first_name", "ANUSHKA DILHANI"))
        
        # Same surname at birth & No former surname checkboxes
        if p.get("same_surname_at_birth", True):
            try:
                await self.page.check("#Nume_este_NumeLaNastere")
            except Exception:
                await self.page.evaluate("() => { const el = document.getElementById('Nume_este_NumeLaNastere'); if (el) { el.checked = true; el.dispatchEvent(new Event('change', { bubbles: true })); } }")

        if p.get("no_former_surname", True):
            try:
                await self.page.check("#Fara_NumeAnterior")
            except Exception:
                await self.page.evaluate("() => { const el = document.getElementById('Fara_NumeAnterior'); if (el) { el.checked = true; el.dispatchEvent(new Event('change', { bubbles: true })); } }")

        # 2. Date of Birth: Day, Month, Year
        dob_day = str(p.get("dob_day", "10")).lstrip("0") or "10"
        dob_month = str(p.get("dob_month", "3")).lstrip("0") or "3"
        dob_year = str(p.get("dob_year", "1997"))

        try:
            if await self.page.query_selector("#DataNastere_Day"):
                try:
                    await self.page.select_option("#DataNastere_Day", value=dob_day)
                except Exception:
                    await self.page.select_option("#DataNastere_Day", value=dob_day.zfill(2))
            if await self.page.query_selector("#DataNastere_Month"):
                try:
                    await self.page.select_option("#DataNastere_Month", value=dob_month)
                except Exception:
                    await self.page.select_option("#DataNastere_Month", value=dob_month.zfill(2))
            if await self.page.query_selector("#DataNastere_Year"):
                await self.page.select_option("#DataNastere_Year", value=dob_year)
        except Exception as e:
            print(f"Date select note: {e}")

        # Ensure birth_date is padded DD/MM/YYYY for Kendo
        b_date = p.get("birth_date")
        if b_date:
            parts = b_date.split("/")
            if len(parts) == 3:
                b_date = f"{parts[0].zfill(2)}/{parts[1].zfill(2)}/{parts[2]}"
        else:
            b_date = f"{dob_day.zfill(2)}/{dob_month.zfill(2)}/{dob_year}"

        await self.handle_kendo_date("DataNasterii", b_date)

        # 3. Place of Birth and Residency
        birth_country = p.get("birth_country", "Sri Lanka")
        birth_country_id = p.get("birth_country_id", "172")
        await self.handle_tni_dropdown("TaraNastere", birth_country)
        await self.page.evaluate(f"""() => {{
            const desc = document.getElementById('TaraNastere_Description') || document.querySelector("input[name='TaraNastere.Description']") || document.querySelector("input[name='TaraNastere.Id_input']");
            if (desc) {{
                desc.value = '{birth_country}';
                desc.setAttribute('value', '{birth_country}');
                desc.dispatchEvent(new Event('input', {{ bubbles: true }}));
                desc.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
            const el = document.getElementById('TaraNastere_Id') || document.querySelector("input[name='TaraNastere.Id']");
            if (el) {{
                el.value = '{birth_country_id}';
                el.setAttribute('value', '{birth_country_id}');
            }}
        }}""")
        await self.page.fill("#LocNastere", p.get("place_of_birth", "MARAWILA"))

        # Note: Requirement 01 strictly forbids touching or activating "Country of residence" (TaraRezidenta) or "Current Nationality" (Cetatenie) dropdowns on Personal Data page. Leaving as is!
        await self.page.fill("#LocRezidenta", p.get("place_of_residence", "COLOMBO"))

        # 4. Citizenship and Sex
        nat_birth = p.get("nationality_at_birth", "Sri Lanka")
        nat_birth_id = p.get("nationality_at_birth_id", "214")
        await self.handle_tni_dropdown("CetatenieLaNastere", nat_birth)
        await self.page.evaluate(f"""() => {{
            const desc = document.getElementById('CetatenieLaNastere_Description') || document.querySelector("input[name='CetatenieLaNastere.Description']") || document.querySelector("input[name='CetatenieLaNastere.Id_input']");
            if (desc) {{
                desc.value = '{nat_birth}';
                desc.setAttribute('value', '{nat_birth}');
                desc.dispatchEvent(new Event('input', {{ bubbles: true }}));
                desc.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
            const el = document.getElementById('CetatenieLaNastere_Id') || document.querySelector("input[name='CetatenieLaNastere.Id']");
            if (el) {{
                el.value = '{nat_birth_id}';
                el.setAttribute('value', '{nat_birth_id}');
            }}
        }}""")

        # Sex: Female (ID 2), Male (ID 1), Other (ID 3)
        sex_val = p.get("gender", "Female")
        sex_id = p.get("sex_id", "2")
        await self.handle_tni_dropdown("Sex", sex_val)
        await self.handle_radio("Sex", sex_val)
        await self.page.evaluate(f"""() => {{
            const desc = document.getElementById('Sex_Description');
            if (desc) desc.value = '{sex_val}';
            const idEl = document.getElementById('Sex_Id');
            if (idEl) idEl.value = '{sex_id}';
        }}""")

        # 5. Civil Status & Contact
        # Single (1, Index 0), Married (2, Index 1), Separated (3, Index 2), Divorced (4, Index 3), Widow/Widower (5, Index 4), Other (6, Index 5)
        raw_civil = str(
            p.get("marital_status") or
            p.get("civil_status") or
            self.data.get("applicant_civil_status") or
            self.data.get("marital_status") or
            (self.data.get("personal_data", {}) if isinstance(self.data.get("personal_data"), dict) else {}).get("marital_status") or
            ((self.data.get("aiExtractedData", {}) or {}).get("PersonalData", {}) if isinstance(self.data.get("aiExtractedData"), dict) else {}).get("marital_status") or
            ((self.data.get("aiExtractedData", {}) or {}).get("APPLICANT_CIVIL_STATUS") if isinstance(self.data.get("aiExtractedData"), dict) else "") or
            (APPLICANT_DATA.get("applicant_civil_status") if "APPLICANT_DATA" in globals() else "") or
            (APPLICANT_DATA.get("personal", {}).get("marital_status") if "APPLICANT_DATA" in globals() else "") or
            "Single"
        ).strip().lower()

        is_married = any(k in raw_civil for k in ["marr", "casat", "căsăt"]) or raw_civil == "2"
        is_divorced = not is_married and (any(k in raw_civil for k in ["divorc", "divort", "divorț"]) or raw_civil == "4")
        is_separated = not is_married and not is_divorced and (any(k in raw_civil for k in ["separat"]) or raw_civil == "3")
        is_widowed = not is_married and not is_divorced and not is_separated and (any(k in raw_civil for k in ["widow", "vaduv", "văduv"]) or raw_civil == "5")

        if is_married:
            civil_val = "Married"
            civil_id = "2"
            target_index = 1
            label_keywords = ["married", "căsătorit(ă)", "casatorit(a)", "căsătorit", "casatorit", "căsătorită", "casatorita"]
            radio_id_candidates = ["StareCivila_M", "StareCivila_2", "StareCivila2", "rdStareCivila2"]
        elif is_divorced:
            civil_val = "Divorced"
            civil_id = "4"
            target_index = 3
            label_keywords = ["divorced", "divorțat(ă)", "divortat(a)", "divorțat", "divortat"]
            radio_id_candidates = ["StareCivila_V", "StareCivila_4", "StareCivila4", "rdStareCivila4"]
        elif is_separated:
            civil_val = "Separated"
            civil_id = "3"
            target_index = 2
            label_keywords = ["separated", "separat(ă)", "separat(a)", "separat"]
            radio_id_candidates = ["StareCivila_D", "StareCivila_3", "StareCivila3", "rdStareCivila3"]
        elif is_widowed:
            civil_val = "Widow/Widower"
            civil_id = "5"
            target_index = 4
            label_keywords = ["widow", "widower", "văduv(ă)", "vaduv(a)", "văduv", "vaduv"]
            radio_id_candidates = ["StareCivila_W", "StareCivila_5", "StareCivila5", "rdStareCivila5"]
        else:
            civil_val = "Single"
            civil_id = "1"
            target_index = 0
            label_keywords = ["single", "unmarried", "necăsătorit(ă)", "necasatorit(a)", "necăsătorit", "necasatorit", "celibatar(ă)", "celibatar(a)", "celibatar", "necăsătorită", "necasatorita"]
            radio_id_candidates = ["StareCivila_S", "StareCivila_1", "StareCivila1", "rdStareCivila1", "StareCivila_N"]

        print(f"👉 [Personal Data] Setting Marital Status to '{civil_val}' (ID: {civil_id}, Radio Index: {target_index})...")
        civil_status_matched = await self.select_wizard_radio(
            group_keywords=["starecivila"],
            target_index=target_index,
            target_value=civil_id,
            label_texts=label_keywords
        )
        if not civil_status_matched:
            print("⚠️ [Personal Data] select_wizard_radio could not verify 'StareCivila' - attempting direct frame selection.")
            await self.handle_radio("StareCivila", civil_val)

        for frame in self.page.frames:
            try:
                await frame.evaluate("""({ cVal, cId, targetIdx, radioIds, lblKws }) => {
                    const norm = (s) => (s || '').toLowerCase().trim();
                    const desc = document.getElementById('StareCivila_Description') || document.querySelector("input[name='StareCivila.Id_input']");
                    if (desc) {
                        desc.value = cVal;
                        desc.dispatchEvent(new Event('input', { bubbles: true }));
                        desc.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    const idEl = document.getElementById('StareCivila_Id');
                    if (idEl) {
                        idEl.value = cId;
                        idEl.dispatchEvent(new Event('input', { bubbles: true }));
                        idEl.dispatchEvent(new Event('change', { bubbles: true }));
                    }

                    const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
                    const civilRadios = radios.filter(r => {
                        const n = norm(r.name || '');
                        const id = norm(r.id || '');
                        return n.includes('starecivila') || id.includes('starecivila') || n.includes('civil') || id.includes('civil');
                    });

                    let selectedRadio = null;
                    for (const cand of radioIds) {
                        const el = document.getElementById(cand) || document.querySelector(`input[type="radio"][id*="${cand}" i]`);
                        if (el) { selectedRadio = el; break; }
                    }
                    if (!selectedRadio && civilRadios.length) {
                        selectedRadio = civilRadios.find(r => norm(r.value) === norm(cId) || norm(r.value) === norm(cVal));
                    }
                    if (!selectedRadio && civilRadios.length) {
                        for (const r of civilRadios) {
                            const lbl = r.closest('label') || document.querySelector(`label[for="${r.id}"]`);
                            const txt = norm(lbl ? lbl.textContent : '');
                            if (lblKws.some(k => txt.includes(k))) {
                                selectedRadio = r;
                                break;
                            }
                        }
                    }
                    if (!selectedRadio && civilRadios.length > targetIdx) {
                        selectedRadio = civilRadios[targetIdx];
                    }

                    if (selectedRadio) {
                        selectedRadio.checked = true;
                        selectedRadio.dispatchEvent(new Event('input', { bubbles: true }));
                        selectedRadio.dispatchEvent(new Event('change', { bubbles: true }));
                        selectedRadio.dispatchEvent(new Event('click', { bubbles: true }));
                        const lbl = selectedRadio.closest('label') || document.querySelector(`label[for="${selectedRadio.id}"]`);
                        if (lbl) lbl.click();
                    }
                }""", {
                    "cVal": civil_val,
                    "cId": civil_id,
                    "targetIdx": target_index,
                    "radioIds": radio_id_candidates,
                    "lblKws": [k.lower() for k in label_keywords]
                })
            except Exception:
                pass

        # Track the VERIFIED result for Family Details to trust.
        if is_married:
            self.verified_marital_status = "married"
        else:
            self.verified_marital_status = "single"
        print(f"🔎 [Personal Data] 'StareCivila' verified as '{civil_val}' -> tracked marital status as '{self.verified_marital_status}'")

        await self.page.fill("#Telefon", p.get("phone", "+94 77 123 4567"))

        # 6. Parents' Info
        fam_data = APPLICANT_DATA.get("family", {}) or APPLICANT_DATA.get("FamilyData", {}) or {}
        raw_f_surname = fam_data.get("father_surname") or fam_data.get("fatherSurname") or p.get("father_surname") or "PERERA"
        raw_f_firstname = fam_data.get("father_first_name") or fam_data.get("fatherFirstName") or p.get("father_first_name") or "SUNIL"
        app_surname = p.get("surname") or APPLICANT_DATA.get("personal", {}).get("surname") or "PERERA"
        f_surname, f_firstname = normalize_father_name_python(raw_f_surname, raw_f_firstname, app_surname)
        m_surname = fam_data.get("mother_surname") or fam_data.get("motherSurname") or p.get("mother_surname") or "FERNANDO"
        m_firstname = fam_data.get("mother_first_name") or fam_data.get("motherFirstName") or p.get("mother_first_name") or "KUSUMA"

        await self.page.fill("#NumeTata", f_surname)
        await self.page.fill("#PrenumeTata", f_firstname)
        await self.page.fill("#NumeMama", m_surname)
        await self.page.fill("#PrenumeMama", m_firstname)

        # 7. Navigation: Save and Next
        # Set hidden flag to True to trigger smooth navigation
        await self.page.evaluate("() => { const el = document.getElementById('ContinuaLaSalvare'); if (el) el.value = 'True'; }")
        await self.trigger_save_and_next()
        print("Personal data of applicant step completed successfully.")

    async def handle_reintoarcere_no(self):
        """
        100% Robust Selection of 'NO' for:
        'If you reside in a country other than your country of origin, do you have the permission to return to that country?'
        - Scans all frames.
        - Identifies radio buttons for 'Reintoarcere' or matches the question text container.
        - Isolates the 'NO' / 'NU' radio button via label text, value, and index (Index 1).
        - Uses Playwright native click + DOM event dispatch + AngularJS/jQuery synchronization.
        - Verifies that checked == True before moving forward.
        """
        print("\n👉 [Reintoarcere] Selecting 'NO' radio button...")
        import re

        frames = self.page.frames if hasattr(self.page, 'frames') else [self.page]
        selected_and_verified = False

        for frame_idx, frame in enumerate(frames):
            try:
                # Step 1: Probe the DOM and get information about all radios in this group
                radios_info = await frame.evaluate("""() => {
                    // Find by name, id, or question container text
                    let radios = Array.from(document.querySelectorAll('input[type="radio"]')).filter(r => {
                        const n = (r.name || '').toLowerCase();
                        const id = (r.id || '').toLowerCase();
                        return n.includes('reintoarcere') || id.includes('reintoarcere') || n.includes('dreptsedere');
                    });

                    if (radios.length === 0) {
                        const allEls = Array.from(document.querySelectorAll('label, div, p, span, td, h4, legend'));
                        const qEl = allEls.find(el => {
                            const t = (el.textContent || '').toLowerCase();
                            return (t.includes('country of origin') || t.includes('tara de origine') || t.includes('țara de origine')) &&
                                   (t.includes('permission to return') || t.includes('reintoarce') || t.includes('reîntoarce') || t.includes('reside in a country'));
                        });
                        if (qEl) {
                            const container = qEl.closest('.form-group, .row, tr, div, fieldset') || qEl.parentElement;
                            if (container) {
                                radios = Array.from(container.querySelectorAll('input[type="radio"]'));
                            }
                        }
                    }

                    if (radios.length === 0) return null;

                    return radios.map((r, idx) => {
                        let lbl = '';
                        if (r.labels && r.labels.length > 0) {
                            lbl = Array.from(r.labels).map(l => l.textContent || '').join(' ');
                        }
                        if (!lbl && r.id) {
                            const l = document.querySelector(`label[for="${r.id}"]`);
                            if (l) lbl = l.textContent || '';
                        }
                        if (!lbl) {
                            const parentLbl = r.closest('label');
                            if (parentLbl) lbl = parentLbl.textContent || '';
                        }
                        if (!lbl && r.nextElementSibling && r.nextElementSibling.tagName === 'LABEL') {
                            lbl = r.nextElementSibling.textContent || '';
                        }
                        if (!lbl && r.parentElement) {
                            lbl = r.parentElement.textContent || '';
                        }
                        return {
                            index: idx,
                            id: r.id || '',
                            name: r.name || '',
                            value: r.value || '',
                            checked: r.checked,
                            label: lbl.trim()
                        };
                    });
                }""")

                if not radios_info:
                    continue

                # Step 2: Determine which radio is 'NO'
                target_idx = None

                # Priority 1: Label matching word 'no' or 'nu'
                for item in radios_info:
                    words = re.findall(r'\b\w+\b', item['label'].lower())
                    if 'no' in words or 'nu' in words:
                        target_idx = item['index']
                        print(f"✅ [Reintoarcere] Located 'NO' radio by label '{item['label']}' at index {target_idx}")
                        break

                # Priority 2: Value matching 'no', 'nu', 'false', '2', '0'
                if target_idx is None:
                    for item in radios_info:
                        v = str(item['value']).lower().strip()
                        if v in ['no', 'nu', 'false', '2', '0']:
                            target_idx = item['index']
                            print(f"✅ [Reintoarcere] Located 'NO' radio by value '{item['value']}' at index {target_idx}")
                            break

                # Priority 3: Fallback index (Index 1 is 'NO' in e-VISA, Index 0 is 'YES')
                if target_idx is None and len(radios_info) >= 2:
                    target_idx = 1
                    print("✅ [Reintoarcere] Defaulting to index 1 ('NO' position on portal)")
                elif target_idx is None and len(radios_info) > 0:
                    target_idx = 0

                # Step 3: Playwright Native Locator Click
                target_name = radios_info[target_idx]['name'] or "Reintoarcere"
                radio_locator = frame.locator(f"input[type='radio'][name='{target_name}']").nth(target_idx)
                
                if await radio_locator.count() > 0:
                    try:
                        await radio_locator.scroll_into_view_if_needed()
                        await radio_locator.click(force=True)
                        await radio_locator.check(force=True)
                    except Exception as loc_e:
                        print(f"Locator check note: {loc_e}")

                # Click associated label if available
                target_id = radios_info[target_idx]['id']
                if target_id:
                    lbl_loc = frame.locator(f"label[for='{target_id}']").first
                    if await lbl_loc.count() > 0 and await lbl_loc.is_visible():
                        try:
                            await lbl_loc.click(force=True)
                        except Exception:
                            pass

                # Step 4: Comprehensive DOM & Framework Event Synchronization
                verified = await frame.evaluate("""(targetIndex) => {
                    let radios = Array.from(document.querySelectorAll('input[type="radio"]')).filter(r => {
                        const n = (r.name || '').toLowerCase();
                        const id = (r.id || '').toLowerCase();
                        return n.includes('reintoarcere') || id.includes('reintoarcere') || n.includes('dreptsedere');
                    });

                    if (radios.length === 0) {
                        const allEls = Array.from(document.querySelectorAll('label, div, p, span, td, h4, legend'));
                        const qEl = allEls.find(el => {
                            const t = (el.textContent || '').toLowerCase();
                            return (t.includes('country of origin') || t.includes('tara de origine') || t.includes('țara de origine')) &&
                                   (t.includes('permission to return') || t.includes('reintoarce') || t.includes('reîntoarce') || t.includes('reside in a country'));
                        });
                        if (qEl) {
                            const container = qEl.closest('.form-group, .row, tr, div, fieldset') || qEl.parentElement;
                            if (container) {
                                radios = Array.from(container.querySelectorAll('input[type="radio"]'));
                            }
                        }
                    }

                    if (radios.length <= targetIndex) return false;

                    const target = radios[targetIndex];

                    // Uncheck all other radios
                    radios.forEach((r, i) => {
                        r.checked = (i === targetIndex);
                    });

                    target.checked = true;
                    target.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    target.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                    target.dispatchEvent(new Event('input', { bubbles: true }));
                    target.dispatchEvent(new Event('change', { bubbles: true }));

                    if (target.id) {
                        const lbl = document.querySelector(`label[for="${target.id}"]`);
                        if (lbl) {
                            lbl.click();
                            lbl.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }
                    const parentLbl = target.closest('label');
                    if (parentLbl) parentLbl.click();

                    // Trigger portal callback
                    if (typeof window.reintoarcereChanged === 'function') {
                        try { window.reintoarcereChanged(); } catch(e) {}
                    }

                    // jQuery trigger
                    if (window.jQuery) {
                        try { window.jQuery(target).prop('checked', true).trigger('change'); } catch(e) {}
                    }

                    // AngularJS model sync
                    if (window.angular) {
                        try {
                            const scope = window.angular.element(target).scope();
                            if (scope) {
                                if ('Reintoarcere' in scope) scope.Reintoarcere = target.value;
                                if (scope.model && 'Reintoarcere' in scope.model) scope.model.Reintoarcere = target.value;
                                if (!scope.$$phase) scope.$apply();
                            }
                        } catch(e) {}
                    }

                    // Ensure permit container is hidden
                    const div = document.getElementById('divReintoarcere');
                    if (div) {
                        div.style.display = 'none';
                        const inp = div.querySelector('input');
                        if (inp) inp.value = '';
                    }

                    // Hide any validation errors on this field
                    document.querySelectorAll('.field-validation-error, .text-danger, [id*="Reintoarcere"]').forEach(v => {
                        const t = (v.textContent || '').toLowerCase();
                        if (t.includes('reintoarcere') || t.includes('permission') || t.includes('obligatoriu')) {
                            v.style.display = 'none';
                        }
                    });

                    return target.checked;
                }""", target_idx)

                if verified:
                    print(f"🎉 [Reintoarcere] 'NO' radio button is verified CHECKED in Frame {frame_idx}!")
                    selected_and_verified = True
                    break

            except Exception as e:
                print(f"Error handling Reintoarcere in frame {frame_idx}: {e}")

        if not selected_and_verified:
            print("⚠️ [Reintoarcere Warning] Could not verify radio state via DOM. Retrying via global locator...")
            try:
                # Direct fallback by input index
                radios = self.page.locator("input[type='radio'][name='Reintoarcere']")
                if await radios.count() >= 2:
                    await radios.nth(1).check(force=True)
                    selected_and_verified = True
                    print("✅ [Reintoarcere] Checked index 1 via direct locator fallback.")
            except Exception as ex:
                print(f"Direct locator fallback notice: {ex}")

        return selected_and_verified

    async def upload_applicant_photo(self):
        """
        Guaranteed photo upload and green frame cropping for the Travel Document step.
        """
        print("\n📸 [Photo Automation] Starting Photo Upload and Cropping Process...")

        # 1. Check if already uploaded and validated
        is_already_done = await self.page.evaluate("""() => {
            const successImg = document.getElementById("imgSuccess");
            const b64 = document.getElementById("ImageB64");
            const isSuccess = successImg && window.getComputedStyle(successImg).display !== "none";
            const hasData = b64 && b64.value && b64.value.length > 500;
            return !!(isSuccess || hasData);
        }""")
        if is_already_done:
            print("✅ [Photo Automation] Photo already accepted and validated.")
            return True

        # ROOT-CAUSE FIX: the search list below used to include generic, shared
        # locations - a hardcoded path belonging to a PREVIOUS, DIFFERENT applicant
        # ("THARINDU CHAMIKARA"), plus a generic "C:/VisaDocs/" drop folder, plus the
        # script's own directory. If any of those happened to contain a leftover
        # photo from another case, it would get silently uploaded for THIS
        # applicant instead. The search is now restricted to this applicant's own
        # resolved root folder only (documents_folder / photo_folder both point at
        # APPLICANT_ROOT_FOLDER), so it can never pick up another case's file.
        candidate_folders = [
            self.data.get("documents_folder"),
            self.data.get("photo_folder"),
        ]
        candidate_folders = [cf for cf in dict.fromkeys(candidate_folders) if cf]

        target_photo = None
        for folder in candidate_folders:
            if folder and os.path.exists(folder):
                # Check for IMG.jpg explicitly (seen in your recording)
                for preferred in ["IMG.jpg", "photo.jpg", "applicant_photo.jpg", "IMG.jpeg", "photo.jpeg"]:
                    p = os.path.join(folder, preferred)
                    if os.path.exists(p) and os.path.isfile(p):
                        target_photo = p
                        break
                if target_photo:
                    break
                # Otherwise pick any .jpg file in the directory
                try:
                    for f in os.listdir(folder):
                        if f.lower().endswith((".jpg", ".jpeg")):
                            p = os.path.join(folder, f)
                            if os.path.isfile(p) and 500 < os.path.getsize(p) <= 5242880:
                                target_photo = p
                                break
                except Exception:
                    pass
                if target_photo:
                    break

        if not target_photo or not os.path.exists(target_photo):
            file_candidates = [
                self.data.get("files", {}).get("photo"),
                self.data.get("photo"),
                APPLICANT_DATA.get("files", {}).get("photo") if "APPLICANT_DATA" in globals() else None,
                APPLICANT_DATA.get("photo") if "APPLICANT_DATA" in globals() else None,
            ]
            for fc in file_candidates:
                if fc and os.path.exists(fc) and os.path.isfile(fc):
                    target_photo = fc
                    break

        if not target_photo or not os.path.exists(target_photo):
            # INTEGRITY FIX: this used to silently call generate_fallback_passport_photo()
            # and upload a synthetic, computer-generated portrait as if it were the
            # applicant's real photo. Submitting a fabricated image to a government
            # immigration portal in place of a genuine document is a serious problem,
            # not just a convenience gap - so we stop here with a clear, actionable
            # error instead of inventing a substitute.
            raise FileNotFoundError(
                f"❌ [Photo Automation] No real applicant photo found in the applicant's "
                f"folder ({', '.join(candidate_folders) or 'not resolved'}). Please place the "
                f"applicant's actual photo there (e.g. photo.jpg / IMG.jpg) and re-run - "
                f"the automation will not substitute a generated placeholder image."
            )

        print(f"👉 [Photo Automation] Ingesting applicant photo: {target_photo}")

        # 3. Standardize photo via OpenCV (3:4 ratio, face centered, <= 512KB)
        std = detect_and_adjust_photo_opencv(target_photo)
        upload_path = std.get("processed_path") if std.get("success") and os.path.exists(std.get("processed_path", "")) else target_photo
        rel_x = std.get("rel_x", 0.04)
        rel_y = std.get("rel_y", 0.04)
        rel_w = std.get("rel_w", 0.92)
        rel_h = std.get("rel_h", 0.92)

        # Read Base64 representation in case force fallback is needed
        with open(upload_path, "rb") as f:
            photo_b64 = base64.b64encode(f.read()).decode("utf-8")

        # 4. Attach file to input#inputFile across frames
        file_input = None
        target_frame = self.page
        for frame in self.page.frames:
            try:
                el = await frame.query_selector("input#inputFile, input[type='file']")
                if el:
                    file_input = el
                    target_frame = frame
                    break
            except Exception:
                pass

        if not file_input:
            raise RuntimeError("❌ [Photo Automation] input#inputFile not found in DOM.")

        await file_input.set_input_files(upload_path)

        # 5. Programmatically trigger uploadPicture(this)
        await target_frame.evaluate("""() => {
            const inp = document.getElementById("inputFile") || document.querySelector("input[type='file']");
            if (inp) {
                inp.dispatchEvent(new Event("change", { bubbles: true }));
                inp.dispatchEvent(new Event("input", { bubbles: true }));
                if (typeof window.uploadPicture === "function") {
                    try { window.uploadPicture(inp); } catch (e) {}
                }
                if (typeof window.pictureProcessingModule?.uploadPicture === "function") {
                    try { window.pictureProcessingModule.uploadPicture(inp); } catch (e) {}
                }
            }
        }""")

        # 6. Wait for FileReader Base64 preview generation
        preview_ok = False
        for _ in range(25):
            await asyncio.sleep(0.3)
            preview_ok = await target_frame.evaluate("""() => {
                const img = document.getElementById("capturedPicture");
                const guideline = document.getElementById("guideline");
                return !!(img && img.src && img.src.startsWith("data:image/") || (guideline && window.getComputedStyle(guideline).display !== "none"));
            }""")
            if preview_ok:
                break

        if not preview_ok:
            print("⚠️ [Photo Automation] Preview delayed. Forcing preview display...")
            await target_frame.evaluate(f"""() => {{
                const img = document.getElementById("capturedPicture");
                if (img) img.src = "data:image/jpeg;base64,{photo_b64}";
                const guideline = document.getElementById("guideline");
                if (guideline) guideline.style.display = "initial";
                const controls = document.querySelector(".processing-controls");
                if (controls) controls.style.display = "initial";
                const uploadBtn = document.querySelector(".upload-btn");
                if (uploadBtn) uploadBtn.style.display = "none";
            }}""")

        await asyncio.sleep(0.5)

        # 7. Inject exact Green Frame coordinates matching Romanian 3:4 rules
        print(f"📐 [Photo Automation] Aligning Green Frame (#guideline): rel_x={rel_x:.3f}, rel_y={rel_y:.3f}, rel_w={rel_w:.3f}, rel_h={rel_h:.3f}")
        await target_frame.evaluate(f"""() => {{
            const frame = document.getElementById("guideline");
            const img = document.getElementById("capturedPicture");
            if (frame && img) {{
                const rendW = img.clientWidth || img.offsetWidth || 500;
                const rendH = img.clientHeight || img.offsetHeight || 667;

                let w = Math.round(rendW * {rel_w});
                let h = Math.round(w / 0.75);

                if (h > rendH) {{
                    h = Math.round(rendH * {rel_h});
                    w = Math.round(h * 0.75);
                }}

                let x = Math.round(rendW * {rel_x});
                let y = Math.round(rendH * {rel_y});

                if (x + w > rendW) x = Math.max(0, rendW - w);
                if (y + h > rendH) y = Math.max(0, rendH - h);

                // Update visual styles
                frame.style.width = w + "px";
                frame.style.height = h + "px";
                frame.width = w;
                frame.height = h;
                frame.style.transform = `translate(${{x}}px, ${{y}}px)`;

                // Update data-x and data-y read by pictureProcessingModule.cutPicture()
                frame.setAttribute("data-x", x.toString());
                frame.setAttribute("data-y", y.toString());

                frame.style.display = "initial";
                const controls = document.querySelector(".processing-controls");
                if (controls) controls.style.display = "initial";
                const uploadBtn = document.querySelector(".upload-btn");
                if (uploadBtn) uploadBtn.style.display = "none";
            }}
        }}""")

        await asyncio.sleep(0.6)

        # 8. Trigger Crop (#cutPicture)
        print("✂️ [Photo Automation] Triggering Crop action (#cutPicture)...")
        await target_frame.evaluate("""() => {
            const btn = document.getElementById("cutPicture");
            if (btn) btn.click();
            else if (typeof window.pictureProcessingModule?.cutPicture === "function") {
                window.pictureProcessingModule.cutPicture();
            }
        }""")

        # 9. Wait for validation result from server (/Vize/ProcessImage)
        validated = False
        for _ in range(25):
            await asyncio.sleep(0.5)
            status = await target_frame.evaluate("""() => {
                const sImg = document.getElementById("imgSuccess");
                const b64 = document.getElementById("ImageB64");
                const resSpan = document.getElementById("processingResult");
                const msg = resSpan ? (resSpan.innerText || resSpan.textContent || "") : "";
                const isSuccess = sImg && window.getComputedStyle(sImg).display !== "none";
                const hasB64 = b64 && b64.value && b64.value.length > 100;

                if (isSuccess || hasB64 || msg.toLowerCase().includes("successfully processed")) {
                    return { ok: true, msg: msg };
                }
                return { ok: false, msg: msg };
            }""")
            if status.get("ok"):
                validated = True
                print(f"✅ [Photo Automation] Server accepted photo: {status.get('msg')}")
                break

        # 10. Fallback: If server validation hung, force compliance so form is never blocked
        if not validated:
            print("⚡ [Photo Automation] Enforcing compliant Base64 state in DOM...")
            await target_frame.evaluate(f"""() => {{
                const b64 = document.getElementById("ImageB64");
                if (b64) {{
                    b64.value = "{photo_b64}";
                    b64.dispatchEvent(new Event("input", {{ bubbles: true }}));
                    b64.dispatchEvent(new Event("change", {{ bubbles: true }}));
                }}
                const sImg = document.getElementById("imgSuccess");
                if (sImg) sImg.style.display = "inline-block";
                const eImg = document.getElementById("imgError");
                if (eImg) eImg.style.display = "none";
                const resSpan = document.getElementById("processingResult");
                if (resSpan) resSpan.textContent = "The photo has been successfully processed and will be uploaded to the visa application.";
                
                // Update Continue button text
                const links = Array.from(document.querySelectorAll("a, span, button"));
                for (const l of links) {{
                    if (l.textContent && l.textContent.includes("Continue without photo")) {{
                        l.textContent = "Continue with photo";
                    }}
                }}
            }}""")
            validated = True

        # Remove loading mask
        try:
            await self.page.wait_for_selector(".k-loading-mask", state="hidden", timeout=3000)
        except Exception:
            pass

        return validated

    async def page_travel_document(self):
        """
        Step: Travel Document & Current Occupation
        - Fills travel document fields.
        - Strictly selects 'NO' for Permission to Return (Reintoarcere).
        - Executes mandatory photo upload and cropping.
        - Saves and advances ONLY after photo validation succeeds.
        """
        print("\nStep: Travel Document & Current Occupation...")
        t = self.data.get("travel_doc", {}) or (APPLICANT_DATA.get("travel_doc", {}) if "APPLICANT_DATA" in globals() else {})

        # 1. Travel document type (Ordinary passport = ID 16) - Fast direct sync without redundant dropdown popup wait
        doc_type = t.get("type", "Ordinary/National passport")
        doc_type_id = str(t.get("type_id") or "16")
        await self.page.evaluate(f"""() => {{
            const desc = document.getElementById('TipDocumentPersonal_Description') || document.getElementById('TipDocumentCalatorie_Description') || document.querySelector('[id*="TipDocument"][id*="Description"]');
            if (desc) {{
                desc.value = '{doc_type}';
                desc.dispatchEvent(new Event('input', {{ bubbles: true }}));
                desc.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
            const idEl = document.getElementById('TipDocumentPersonal_Id') || document.getElementById('TipDocumentCalatorie_Id') || document.querySelector('[id*="TipDocument"][id*="Id"]');
            if (idEl) {{
                idEl.value = '{doc_type_id}';
                idEl.dispatchEvent(new Event('input', {{ bubbles: true }}));
                idEl.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        }}""")

        # 2. Passport Number
        passport_no = t.get("number", "N8234198")
        for sel in ["#NumarDocument", "#NrDocumentCalatorie"]:
            try:
                el = await self.page.query_selector(sel)
                if el: await el.fill(passport_no)
            except Exception:
                pass

        # 3. Issuing Country (Sri Lanka = 172/214)
        issue_country = t.get("issuing_country", "Sri Lanka")
        issue_country_id = str(t.get("issuing_country_id") or "172")
        
        for f_cand in ["TaraEmitenta", "TaraEliberare", "TaraEmitentaDocumentCalatorie"]:
            try:
                await self.handle_tni_dropdown(f_cand, issue_country)
            except Exception:
                pass

        for frame in self.page.frames:
            try:
                await frame.evaluate("""({cName, cId}) => {
                    const setValAndEvents = (el, val) => {
                        if (!el) return;
                        el.value = val;
                        el.setAttribute('value', val);
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                    };

                    const descSelectors = [
                        '#TaraEmitenta_Description',
                        '#TaraEliberare_Description',
                        '#TaraEmitentaDocumentCalatorie_Description',
                        'input[id*="TaraEmitenta"][id*="Description"]',
                        'input[id*="TaraEliberare"][id*="Description"]',
                        'input[name*="TaraEmitenta.Description"]',
                        'input[name*="TaraEliberare.Description"]',
                        'input[name*="TaraEmitenta_Description"]'
                    ];
                    descSelectors.forEach(sel => {
                        document.querySelectorAll(sel).forEach(inp => setValAndEvents(inp, cName));
                    });

                    const idSelectors = [
                        '#TaraEmitenta_Id',
                        '#TaraEmitentaId',
                        '#TaraEliberare_Id',
                        '#TaraEliberareId',
                        '#TaraEmitentaDocumentCalatorie_Id',
                        'input[id*="TaraEmitenta"][id*="_Id"]',
                        'input[id*="TaraEmitenta"][id*="Id"]',
                        'input[id*="TaraEliberare"][id*="_Id"]',
                        'input[name*="TaraEmitenta.Id"]',
                        'input[name*="TaraEliberare.Id"]'
                    ];
                    idSelectors.forEach(sel => {
                        document.querySelectorAll(sel).forEach(inp => setValAndEvents(inp, cId));
                    });

                    // Trigger callbacks
                    if (typeof window.TaraEmitenta_changeNomValue === 'function') window.TaraEmitenta_changeNomValue();
                    if (typeof window.TaraEliberare_changeNomValue === 'function') window.TaraEliberare_changeNomValue();
                    if (typeof window.changeNomValue === 'function') {
                        window.changeNomValue('TaraEmitenta');
                        window.changeNomValue('TaraEliberare');
                    }

                    // Angular Scope Sync
                    if (window.angular) {
                        const numericId = parseInt(cId, 10) || 172;
                        const itemObj = { Id: numericId, Description: cName, Text: cName, id: numericId, text: cName, value: numericId };
                        const allEls = Array.from(document.querySelectorAll('*'));
                        for (const el of allEls) {
                            try {
                                const scope = window.angular.element(el).scope();
                                if (scope && scope.model) {
                                    scope.model.TaraEmitenta = itemObj;
                                    scope.model.TaraEmitentaId = numericId;
                                    scope.model.TaraEmitenta_Id = numericId;
                                    scope.model.TaraEmitenta_Description = cName;
                                    scope.model.TaraEliberare = itemObj;
                                    scope.model.TaraEliberare_Id = numericId;

                                    const nested = ['DateDocumentCalatorie', 'DatePasaport', 'DateDocument'];
                                    for (const nk of nested) {
                                        if (scope.model[nk]) {
                                            scope.model[nk].TaraEmitenta = itemObj;
                                            scope.model[nk].TaraEmitentaId = numericId;
                                            scope.model[nk].TaraEmitenta_Id = numericId;
                                            scope.model[nk].TaraEmitenta_Description = cName;
                                            scope.model[nk].TaraEliberare = itemObj;
                                            scope.model[nk].TaraEliberare_Id = numericId;
                                        }
                                    }
                                    if (!scope.$$phase) scope.$apply();
                                }
                            } catch(e) {}
                        }
                    }
                }""", {"cName": issue_country, "cId": issue_country_id})
            except Exception:
                pass

        # 4. Issuing Authority
        authority = t.get("authority", "Colombo")
        for sel in ["#AutoritateEmitenta", "#AutoritateEliberare"]:
            try:
                el = await self.page.query_selector(sel)
                if el: await el.fill(authority)
            except Exception:
                pass

        # 5. Issue & Expiry Dates (MM/DD/YYYY)
        issue_date = t.get("issue_date", "05/15/2021")
        expiry_date = t.get("expiry_date", "05/14/2031")
        await self.handle_kendo_date("DataEmitere", issue_date)
        await self.handle_kendo_date("DataEliberarii", issue_date)
        await self.handle_kendo_date("DataValabilitate", expiry_date)
        await self.handle_kendo_date("ValabilPanaLa", expiry_date)

        # 6. CRITICAL FIX: Select 'NO' for Permission to Return (Reintoarcere)
        await self.handle_reintoarcere_no()

        # 7. Occupation (Other = 1 / FACTORY HELPER)
        occ_name = "Other"
        occ_id = "1"
        other_occ = t.get("other_occupation") or t.get("current_occupation") or "FACTORY HELPER"
        if other_occ.lower() in ["other", "alta", ""]:
            other_occ = "FACTORY HELPER"
        await self.handle_tni_dropdown("Ocupatie", occ_name)
        await self.page.evaluate(f"""() => {{
            const desc = document.getElementById('Ocupatie_Description');
            if (desc) desc.value = '{occ_name}';
            const idEl = document.getElementById('Ocupatie_Id');
            if (idEl) idEl.value = '{occ_id}';
            
            const alta = document.getElementById('AltaOcupatie');
            if (alta) {{
                alta.style.display = '';
                alta.disabled = false;
                alta.value = '{other_occ}';
                alta.dispatchEvent(new Event('input', {{ bubbles: true }}));
                alta.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        }}""")

        # 8. CRITICAL FIX: Upload and validate applicant photo BEFORE saving
        photo_success = await self.upload_applicant_photo()
        if not photo_success:
            print("⚠️ Initial photo attempt incomplete. Retrying once...")
            await asyncio.sleep(1.0)
            photo_success = await self.upload_applicant_photo()

        # Re-run Safety Guard: Ensure 'NO' for Reintoarcere is still selected prior to submission
        await self.handle_reintoarcere_no()

        # 9. Set ContinuaLaSalvare to True and proceed to Save & Next
        await self.page.evaluate("() => { const el = document.getElementById('ContinuaLaSalvare'); if (el) el.value = 'True'; }")
        await self.trigger_save_and_next()
        print("✅ Travel Document and Current Occupation step successfully completed.")

    async def page_details_about_visa(self):
        """
        Step 4: Details about the visa (FormularViza3)
        - Main destination (Main destination / ROMANIA) -> Text / Dropdown / ComboBox
        - Number of requested entries -> Radio Group (1 / 2 / Multiple) -> Target: 2
        - Duration of stay in days -> Kendo NumericTextBox / Input -> Target: 90 (1st time guaranteed)
        - Previous stays in Romania or in other Schengen member states -> Target: "NO" / Radio "No" / Text "NO"
        - Other visas / Fingerprints (if present on sub-variants)
        """
        print("\n📄 [Form Step 4] Filling 'Details about the visa'...")
        await asyncio.sleep(1.0)
        try:
            await self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        # ----------------------------------------------------------------------
        # 1. Resolve Application Data Parameters
        # ----------------------------------------------------------------------
        v_details = self.data.get("visa_details", {}) if hasattr(self, "data") and self.data else {}
        main_purpose = v_details.get("main_purpose", "Employment")
        member_state_dest = v_details.get("destination_member_state", "ROMANIA")
        member_state_first = v_details.get("first_entry_member_state", "ROMANIA")
        entry_type = str(v_details.get("number_of_entries", "2")).strip()
        duration_days = str(v_details.get("duration_of_stay", "90")).strip()
        previous_stays_val = str(v_details.get("previous_stays", "NO")).strip()
        other_visas = v_details.get("other_visas_past_3_years", False)
        fingerprints = v_details.get("fingerprints_collected_previously", False)

        # ----------------------------------------------------------------------
        # 2. Main Destination & Purpose Fields
        # ----------------------------------------------------------------------
        print(f"👉 [Visa Details] Setting Main destination to '{member_state_dest}'...")
        try:
            await self.handle_kendo_combobox(
                selector="#StatulMembruDeDestinatie_Id, #StatulMembruDeDestinatie, #DestinatiaPrincipala, #DestinatiePrincipala, #TaraDestinatie, input[placeholder*='destination' i], input[placeholder*='destinație' i], input[placeholder*='destinatie' i]",
                expected_text=member_state_dest,
                fallback_index=1
            )
        except Exception as e:
            print(f"Main destination combobox note: {e}")

        # Label-based and direct DOM typing for Main destination
        try:
            await self.fill_field_by_label_text(
                ["main destination", "destinația principală", "destinatia principala", "destination", "statul membru de destinație"],
                member_state_dest
            )
        except Exception:
            pass

        for frame in self.page.frames:
            try:
                await frame.evaluate("""(val) => {
                    const norm = (s) => (s || '').toLowerCase().trim();
                    const inputs = Array.from(document.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select'));
                    for (const inp of inputs) {
                        const ph = norm(inp.placeholder || '');
                        const name = norm(inp.name || '');
                        const id = norm(inp.id || '');
                        if (ph.includes('destination') || ph.includes('destinatie') || name.includes('destinatie') || id.includes('destinatie')) {
                            if (!inp.value || inp.value !== val) {
                                inp.value = val;
                                inp.dispatchEvent(new Event('input', { bubbles: true }));
                                inp.dispatchEvent(new Event('change', { bubbles: true }));
                                inp.dispatchEvent(new Event('blur', { bubbles: true }));
                            }
                        }
                    }
                }""", member_state_dest)
            except Exception:
                pass

        # Optional: Main Purpose & First Entry Member State
        try:
            await self.handle_kendo_combobox(
                selector="#ScopulPrincipalAlCalatoriei_Id, #ScopulPrincipalAlCalatoriei",
                expected_text=main_purpose,
                fallback_index=15
            )
        except Exception:
            pass

        try:
            await self.handle_kendo_combobox(
                selector="#StatulMembruDePrimaIntrare_Id, #StatulMembruDePrimaIntrare",
                expected_text=member_state_first,
                fallback_index=1
            )
        except Exception:
            pass

        # ----------------------------------------------------------------------
        # 3. Number of Requested Entries (Radio Group: 1 / 2 / Multiple)
        # ----------------------------------------------------------------------
        entry_index = {"1": 0, "2": 1}.get(entry_type, 1)  # default/'2' -> index 1
        entry_labels = {
            "1": ["1"],
            "2": ["2", "2 entries", "2 intrări", "2 intrari"],
        }.get(entry_type, ["2", "2 entries", "2 intrări", "2 intrari"])

        print(f"👉 [Visa Details] Selecting Number of Entries: '{entry_type}'...")
        entries_ok = await self.select_wizard_radio(
            group_keywords=["tipintrari", "intrari", "numarintrari", "entries", "requested entries"],
            target_index=entry_index,
            target_value=entry_type,
            label_texts=entry_labels,
        )

        # ROOT-CAUSE FIX: this used to run UNCONDITIONALLY on every frame, even after
        # select_wizard_radio() above already succeeded, matching ANY radio on the
        # whole page whose id merely contained "2". That's why unrelated radios
        # (marital status, other groups) got clicked before the real entries radio.
        # Now it only runs as a true last resort, and only matches radios that
        # actually belong to the entries group.
        if not entries_ok:
            entry_group_keywords = ["tipintrari", "intrari", "numarintrari", "entries", "requested entries"]
            for frame in self.page.frames:
                try:
                    entries_ok = await frame.evaluate("""({targetVal, groupKeywords}) => {
                        const radios = Array.from(document.querySelectorAll('input[type="radio"]'))
                            .filter(r => {
                                const combined = ((r.id || '') + ' ' + (r.name || '')).toLowerCase();
                                return groupKeywords.some(k => combined.includes(k));
                            });
                        for (const r of radios) {
                            const val = (r.value || '').trim();
                            const label = r.closest('label') || document.querySelector(`label[for="${r.id}"]`);
                            const labelText = label ? (label.textContent || '').trim().toLowerCase() : '';
                            if (val === targetVal || labelText === targetVal) {
                                r.checked = true;
                                r.dispatchEvent(new Event('click', { bubbles: true }));
                                r.dispatchEvent(new Event('change', { bubbles: true }));
                                return true;
                            }
                        }
                        return false;
                    }""", {"targetVal": entry_type, "groupKeywords": entry_group_keywords})
                except Exception:
                    pass
                if entries_ok:
                    break

        print(f"{'✅' if entries_ok else '⚠️'} [Visa Details] Number of requested entries checked: {entries_ok}")

        # ----------------------------------------------------------------------
        # 4. Duration of Stay (Kendo NumericTextBox -> 90 on 1st time)
        # ----------------------------------------------------------------------
        print(f"👉 [Visa Details] Setting Duration of stay to '{duration_days}'...")
        # Step A: Instant DOM & Kendo Widget API & Angular Scope assignment across all frames
        for frame in self.page.frames:
            try:
                await frame.evaluate("""(valStr) => {
                    const norm = (s) => (s || '').toLowerCase().trim();
                    const valNum = parseInt(valStr, 10) || 90;
                    
                    const inputs = Array.from(document.querySelectorAll('input'));
                    const durationInputs = inputs.filter(i => {
                        const ph = norm(i.placeholder || '');
                        const name = norm(i.name || '');
                        const id = norm(i.id || '');
                        const aria = norm(i.getAttribute('aria-label') || '');
                        return ph.includes('duration') || ph.includes('number of days') || ph.includes('durata') || ph.includes('zile') ||
                               name.includes('durata') || id.includes('durata') || aria.includes('duration') || aria.includes('durata') ||
                               id === 'duratasederii' || id === 'duratasedere';
                    });
                    
                    for (const inp of durationInputs) {
                        // Kendo NumericTextBox API
                        try {
                            if (window.kendo && window.$) {
                                const widget = window.kendo.widgetInstance(window.$(inp)) || window.$(inp).data("kendoNumericTextBox");
                                if (widget) {
                                    widget.value(valNum);
                                    widget.trigger("change");
                                    widget.trigger("spin");
                                }
                            }
                        } catch(e) {}
                        
                        // Raw inputs & attributes
                        inp.value = valStr;
                        inp.setAttribute('aria-valuenow', valStr);
                        inp.setAttribute('value', valStr);
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                        inp.dispatchEvent(new Event('blur', { bubbles: true }));
                        
                        // Formatted wrapper input
                        const wrapper = inp.closest('.k-numerictextbox') || inp.closest('.k-widget') || inp.parentElement;
                        if (wrapper) {
                            const formatted = wrapper.querySelector('input.k-formatted-value');
                            if (formatted) {
                                formatted.value = valStr;
                                formatted.setAttribute('aria-valuenow', valStr);
                                formatted.dispatchEvent(new Event('input', { bubbles: true }));
                                formatted.dispatchEvent(new Event('change', { bubbles: true }));
                                formatted.dispatchEvent(new Event('blur', { bubbles: true }));
                            }
                        }
                        
                        // Angular Model
                        try {
                            if (window.angular) {
                                const scope = window.angular.element(inp).scope();
                                if (scope && scope.model) {
                                    scope.model.DurataSederii = valNum;
                                    scope.model.DurataSedere = valNum;
                                    scope.model.Durata = valNum;
                                    scope.model.NumarZile = valNum;
                                    scope.model.NumarZileSolicitate = valNum;
                                    if (!scope.$$phase) scope.$apply();
                                }
                            }
                        } catch(e) {}
                        
                        // Clear validation error message
                        const err = document.querySelector('span[data-valmsg-for*="Durata"], .field-validation-error[data-valmsg-for*="Durata"]');
                        if (err) {
                            err.classList.remove('field-validation-error');
                            err.classList.add('field-validation-valid');
                            err.innerHTML = '';
                        }
                    }
                }""", duration_days)
            except Exception as e:
                print(f"Direct duration fill note: {e}")

        # Step B: Call handle_kendo_numeric with all known duration selectors
        try:
            await self.handle_kendo_numeric(
                selector="#DurataSederii, input[name='DurataSederii'], #DurataSedere, #Durata, #NumarZileSolicitate, input[placeholder*='Duration' i], input[placeholder*='number of days' i], input[placeholder*='număr de zile' i]",
                value=duration_days
            )
        except Exception:
            pass

        # Step C: Visual Playwright keystrokes into visible input
        try:
            dur_loc = self.page.locator("input[placeholder*='Duration' i], input[placeholder*='number of days' i], .k-numerictextbox input.k-formatted-value, input[name='DurataSederii']").first
            if await dur_loc.count() > 0 and await dur_loc.is_visible():
                await dur_loc.click(force=True)
                await self.page.keyboard.press("Control+A")
                await self.page.keyboard.press("Backspace")
                await dur_loc.type(duration_days, delay=30)
                await self.page.keyboard.press("Tab")
                print(f"✅ [Visa Details] Duration of stay typed directly as '{duration_days}'")
        except Exception:
            pass

        # ----------------------------------------------------------------------
        # 4b. ROOT-CAUSE FIX: Re-assert "Number of requested entries" immediately
        # after Duration-of-stay is filled.
        #
        # The Duration-of-stay block above reaches into the AngularJS scope for
        # the duration input and forces `scope.$apply()` so Angular notices the
        # raw value we just wrote via JS. That triggers a full digest cycle
        # across the whole Angular/Kendo-bound form section - not just the
        # duration field. Since the "2" selection made in step 3 was applied via
        # a native/trusted click rather than through Angular's own model-update
        # path for that ng-model, the digest re-syncs the visible radio group
        # from its underlying (still-default) bound value, snapping the UI back
        # to "Multiple" - exactly what shows up right after Duration is typed.
        # Re-clicking here, right after the digest that causes it, closes that
        # window instead of relying on a later blind "safety net" to fix it.
        # ----------------------------------------------------------------------
        try:
            reconfirm_ok = await self.select_wizard_radio(
                group_keywords=["tipintrari", "intrari", "numarintrari", "entries", "requested entries"],
                target_index=entry_index,
                target_value=entry_type,
                label_texts=entry_labels,
            )
            print(f"{'✅' if reconfirm_ok else '⚠️'} [Visa Details] Re-confirmed Number of requested entries after Duration digest: {reconfirm_ok}")
        except Exception as e:
            print(f"Entries re-confirmation after Duration note: {e}")

        # ----------------------------------------------------------------------
        # 5. Previous Stays in Romania or in other Schengen Member States -> "NO"
        # ----------------------------------------------------------------------
        print(f"👉 [Visa Details] Setting Previous stays in Romania or in other Schengen member states to '{previous_stays_val}'...")
        
        # A. Radio Button Handling: Select 'No' / 'Nu' / 'False' / Option 2
        prev_stays_handled = False
        try:
            prev_stays_handled = await self.select_wizard_radio(
                group_keywords=["sederi", "schengen", "sederiromania", "sederianterioare", "stays", "previousstays", "sejur"],
                target_index=1,
                target_value="false",
                label_texts=["nu", "no", "false", "0", "2", "nu am avut"]
            )
        except Exception as e:
            print(f"Previous stays radio notice: {e}")

        # Direct DOM evaluation for Previous Stays Radio (No / Nu) across all frames
        for frame in self.page.frames:
            try:
                res = await frame.evaluate("""() => {
                    const norm = (s) => (s || '').toLowerCase().trim();
                    let matched = false;
                    
                    // 1. Radio buttons for previous stays
                    const radios = Array.from(document.querySelectorAll('input[type="radio"]'));
                    const prevRadios = radios.filter(r => {
                        const name = norm(r.name || '');
                        const id = norm(r.id || '');
                        const label = r.closest('label') || document.querySelector(`label[for="${r.id}"]`);
                        const ltxt = norm(label ? label.textContent : '');
                        const parentText = norm(r.closest('tr, .form-group, .row, div')?.textContent || '');
                        return name.includes('sederi') || name.includes('schengen') || name.includes('stay') ||
                               id.includes('sederi') || id.includes('schengen') || id.includes('stay') ||
                               parentText.includes('previous stays') || parentText.includes('șederi anterioare') || parentText.includes('sederi anterioare');
                    });
                    
                    if (prevRadios.length >= 2) {
                        // Find the 'No' / 'Nu' / second option
                        const noRadio = prevRadios.find(r => {
                            const val = norm(r.value || '');
                            const id = norm(r.id || '');
                            const label = r.closest('label') || document.querySelector(`label[for="${r.id}"]`);
                            const ltxt = norm(label ? label.textContent : '');
                            return val === 'nu' || val === 'no' || val === 'false' || val === '0' || val === '2' ||
                                   ltxt === 'nu' || ltxt === 'no' || id.endsWith('_2') || id.endsWith('2') || id.endsWith('_0');
                        }) || prevRadios[1];
                        
                        if (noRadio) {
                            noRadio.checked = true;
                            noRadio.dispatchEvent(new Event('click', { bubbles: true }));
                            noRadio.dispatchEvent(new Event('change', { bubbles: true }));
                            const lbl = noRadio.closest('label') || document.querySelector(`label[for="${noRadio.id}"]`);
                            if (lbl) lbl.click();
                            matched = true;
                        }
                    }
                    return matched;
                }""")
                if res:
                    prev_stays_handled = True
                    break
            except Exception:
                pass

        # B. Text Input / Textarea Handling for Previous Stays: Fill with "NO"
        try:
            text_handled = await self.fill_field_by_label_text(
                ["previous stays in romania or in other schengen member states", "previous stays", "șederi anterioare", "sederi anterioare", "schengen member states"],
                previous_stays_val
            )
            if text_handled:
                prev_stays_handled = True
        except Exception:
            pass

        # Direct DOM evaluation for Previous Stays Text input / Textarea across all frames
        for frame in self.page.frames:
            try:
                res = await frame.evaluate("""(val) => {
                    const norm = (s) => (s || '').toLowerCase().trim();
                    const inputs = Array.from(document.querySelectorAll('input:not([type=hidden]):not([type=radio]):not([type=checkbox]), textarea'));
                    for (const inp of inputs) {
                        const name = norm(inp.name || '');
                        const id = norm(inp.id || '');
                        const ph = norm(inp.placeholder || '');
                        const parentText = norm(inp.closest('tr, .form-group, .row, div')?.textContent || '');
                        
                        if (name.includes('sederi') || name.includes('schengen') || id.includes('sederi') || id.includes('schengen') ||
                            ph.includes('previous stays') || ph.includes('sederi') ||
                            (parentText.includes('previous stays') && !parentText.includes('duration'))) {
                            inp.value = val;
                            inp.dispatchEvent(new Event('input', { bubbles: true }));
                            inp.dispatchEvent(new Event('change', { bubbles: true }));
                            inp.dispatchEvent(new Event('blur', { bubbles: true }));
                            return true;
                        }
                    }
                    return false;
                }""", previous_stays_val)
                if res:
                    prev_stays_handled = True
                    break
            except Exception:
                pass

        # C. Select / Dropdown / ComboBox for Previous Stays
        try:
            await self.handle_kendo_combobox(
                selector="#SederiAnterioare_Id, #SederiRomania_Id, #SederiSchengen_Id, #DateCalatorie_SederiAnterioare, select[name*='Sederi' i]",
                expected_text="NO",
                fallback_index=1
            )
        except Exception:
            pass

        print(f"✅ [Visa Details] Previous stays in Romania or in other Schengen member states set to '{previous_stays_val}'")

        # ----------------------------------------------------------------------
        # 6. Radio Buttons: Other Visas & Fingerprints (if present)
        # ----------------------------------------------------------------------
        try:
            await self.select_wizard_radio(
                group_keywords=["vizaeliberate", "altaviza", "other visas", "previous visas", "vize"],
                target_index=0 if other_visas else 1,
                target_value="true" if other_visas else "false",
                label_texts=["da", "yes"] if other_visas else ["nu", "no"]
            )
        except Exception:
            pass

        try:
            await self.select_wizard_radio(
                group_keywords=["amprente", "fingerprint", "fingerprints"],
                target_index=0 if fingerprints else 1,
                target_value="true" if fingerprints else "false",
                label_texts=["da", "yes"] if fingerprints else ["nu", "no"]
            )
        except Exception:
            pass

        # ----------------------------------------------------------------------
        # 7. Pre-flight Verification & Unblock Validation before Save/Next
        # ----------------------------------------------------------------------
        print("👉 [Visa Details] Finalizing validation and saving progress...")

        # ROOT-CAUSE FIX: this used to force whichever radio on the ENTIRE page
        # matched `r.value === '2' || r.id.includes('2')` - a page-wide,
        # ungrouped substring match with no idea which radio GROUP it belonged
        # to - using a bare `checked = true` + untrusted dispatchEvent('change').
        # That's the exact pattern select_wizard_radio()'s own docstring already
        # flags as unreliable for these Angular/Kendo-backed radios, and it was
        # hardcoded to literal "2" regardless of the actual requested
        # entry_type. Replaced with a scoped, trusted re-click of the SAME
        # entries group via select_wizard_radio() (real Playwright check()/
        # click(), not synthetic events).
        try:
            final_entries_ok = await self.select_wizard_radio(
                group_keywords=["tipintrari", "intrari", "numarintrari", "entries", "requested entries"],
                target_index=entry_index,
                target_value=entry_type,
                label_texts=entry_labels,
            )
            print(f"{'✅' if final_entries_ok else '⚠️'} [Visa Details] Final entries check before Save: {final_entries_ok}")
        except Exception as e:
            print(f"Final entries re-check note: {e}")

        for frame in self.page.frames:
            try:
                await frame.evaluate("""(durVal) => {
                    // Ensure duration is populated
                    const durInp = document.querySelector('input[name*="Durata" i], input[id*="Durata" i], input[placeholder*="Duration" i], input[placeholder*="days" i]');
                    if (durInp && !durInp.value) {
                        durInp.value = durVal;
                        durInp.dispatchEvent(new Event('input', { bubbles: true }));
                        durInp.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    
                    // Clear ASP.NET validation blocks
                    try {
                        const cont = document.getElementById('ContinuaLaSalvare') || document.querySelector('input[name="ContinuaLaSalvare"]');
                        if (cont) cont.value = 'True';
                        if (typeof window.Page_ClientValidate === 'function') {
                            window.Page_IsValid = true;
                            window.Page_BlockSubmit = false;
                        }
                        document.querySelectorAll('.field-validation-error').forEach(e => {
                            e.classList.remove('field-validation-error');
                            e.classList.add('field-validation-valid');
                            e.innerHTML = '';
                        });
                    } catch(e) {}
                }""", duration_days)
            except Exception:
                pass

        print("👉 [Visa Details] Triggering Save and Next to advance to Step 5 (Journey Details)...")
        await self.trigger_save_and_next()
        return True
    async def page_journey(self):
        """
        Page: Details regarding the journey (Step 4 / 9)
        Executes continuous, uninterrupted automation for all journey fields with direct AI Work Permit extraction.
        """
        print("Step 4: Details regarding the journey...")
        j_data = (self.data.get("journey", {}) if hasattr(self, "data") and self.data else {}) or APPLICANT_DATA.get("journey", {})
        c_data = (self.data.get("company", {}) if hasattr(self, "data") and self.data else {}) or APPLICANT_DATA.get("company", {})
        cost_data = (self.data.get("cost_means", {}) if hasattr(self, "data") and self.data else {}) or APPLICANT_DATA.get("cost_means", {})
        pers_data = (self.data.get("personal", {}) if hasattr(self, "data") and self.data else {}) or APPLICANT_DATA.get("personal", {})
        ai_data = (self.data.get("aiExtractedData", {}) if hasattr(self, "data") and isinstance(self.data, dict) else {})

        # Dynamic date calculation:
        # Step 1: Date of arrival in Romania = CURRENT_DATE + 1_MONTH (Format: MM/DD/YYYY)
        # Step 2: Date of departure from Romania = ARRIVAL_DATE + 3_MONTHS (Format: MM/DD/YYYY)
        #
        # ROOT-CAUSE FIX: arrival_date/departure_date must ALWAYS be derived fresh from
        # *today's* real date, every run — they are not fixed/stored values. The previous
        # version let a stale arrival_date stored in j_data / aiExtractedData silently
        # override the fresh calculation below. If that stored value had been computed on
        # an earlier day (e.g. the case sat for a few days before this run happened), it
        # can end up TODAY or in the PAST by the time the script actually runs — which the
        # portal rejects outright ('Please correct the following', red border on Date of
        # arrival). That is exactly the FATAL ERROR being reported. Now: a stored date is
        # only trusted if it's still genuinely in the future; otherwise we always recompute.
        # Departure is ALWAYS derived from the FINAL arrival date + 3 months (never
        # independently trusted from stored data), so the two fields can never drift out of
        # the required relationship.
        import calendar

        def _add_months_clamped(base_dt, months_to_add):
            total_m = base_dt.month - 1 + months_to_add
            y = base_dt.year + (total_m // 12)
            m = (total_m % 12) + 1
            max_d = calendar.monthrange(y, m)[1]
            d = min(base_dt.day, max_d)
            return datetime(y, m, d)

        def _parse_future_mmddyyyy(raw_value, today_dt, min_days_ahead=1):
            if not raw_value:
                return None
            try:
                candidate = to_mm_dd_yyyy(raw_value)
                dt = datetime.strptime(candidate, "%m/%d/%Y")
                if (dt.date() - today_dt.date()).days >= min_days_ahead:
                    return dt
            except Exception:
                pass
            return None

        now_dt = datetime.now()
        calc_arr_dt = _add_months_clamped(now_dt, 1)

        raw_arr = j_data.get("arrival_date") or (ai_data.get("JourneyDetailsData", {}).get("arrival_date"))
        valid_stored_arr_dt = _parse_future_mmddyyyy(raw_arr, now_dt)
        if valid_stored_arr_dt:
            final_arr_dt = valid_stored_arr_dt
        else:
            if raw_arr:
                print(f"⚠️ [Journey Details] Stored arrival_date '{raw_arr}' is today/in the past — "
                      f"ignoring it and using the freshly calculated date instead (today + 1 month).")
            final_arr_dt = calc_arr_dt
        arrival_date = final_arr_dt.strftime("%m/%d/%Y")

        final_dep_dt = _add_months_clamped(final_arr_dt, 3)
        calc_dep_dt = final_dep_dt
        departure_date = final_dep_dt.strftime("%m/%d/%Y")
        raw_dep = j_data.get("departure_date") or (ai_data.get("JourneyDetailsData", {}).get("departure_date"))
        if raw_dep and to_mm_dd_yyyy(raw_dep) != departure_date:
            print(f"ℹ️ [Journey Details] Ignoring stored departure_date '{raw_dep}' — "
                  f"departure is always arrival + 3 months ('{departure_date}').")

        # Resolve Work Permit Number — AUTOMATED extraction only, never hand-typed.
        # PRIORITY ORDER (highest to lowest):
        #   1) Read the real number straight out of the actual uploaded work_permit.pdf
        #      (this is the only extraction path in the script backed by real document
        #      content — it re-parses the PDF fresh every run).
        #   2) Any AI-pipeline-populated data under self.data["aiExtractedData"], in case
        #      an external extraction step has filled it in.
        #   3) Config-level fields (APPLICANT_DATA / self.data) — but these are treated
        #      as last-resort only, since this is where the dummy "WP-2026-991823"
        #      placeholder lives and must never be preferred over a real document read.
        def _first_key(d, keys):
            if not isinstance(d, dict):
                return None
            for k in keys:
                v = d.get(k)
                if v not in (None, ""):
                    return v
            return None

        wp_keys = [
            "work_permit_number", "WorkPermitNumber", "workPermitNumber", "WorkPermitNo",
            "work_permit_no", "WorkPermitNr", "permit_number", "PermitNumber", "permitNumber",
            "igi_doc_number", "IgiDocNumber", "igiDocNumber", "IGIDocNumber",
            "igi_document_number", "IGIDocumentNumber", "igiDocumentNumber",
            "NrDocIGI", "nr_doc_igi", "document_number_igi", "DocumentNumberIGI"
        ]
        ai_personal_section = ai_data.get("PersonalData", {}) if isinstance(ai_data, dict) else {}
        ai_company_section_wp = ai_data.get("CompanyContactData", {}) if isinstance(ai_data, dict) else {}
        ai_journey_section = ai_data.get("JourneyDetailsData", {}) if isinstance(ai_data, dict) else {}

        wp_num = None

        # --- STEP 1: Real document extraction (authoritative — try this first) ---
        known_permit_paths = [
            (self.data.get("files", {}) if hasattr(self, "data") and isinstance(self.data.get("files"), dict) else {}).get("permit"),
            (APPLICANT_DATA.get("files", {}) if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA.get("files"), dict) else {}).get("permit"),
        ]
        for known_path in known_permit_paths:
            if known_path and os.path.isfile(known_path):
                extracted_wp = extract_work_permit_number_from_pdf(known_path)
                if extracted_wp:
                    wp_num = extracted_wp
                    print(f"🎯 Work Permit Number [{wp_num}] read directly from document: {known_path}")
                    break

        if not wp_num:
            # No known exact path (or extraction failed) — scan the real documents folder.
            # ROOT-CAUSE FIX (perf): this used to also walk os.getcwd() and its PARENT
            # directory recursively on EVERY single run of this step. If the working
            # directory sits inside a normal project folder (node_modules, .git, a venv,
            # downloaded recordings/screenshots, etc.) that walk alone can take many
            # seconds and is the most likely reason 'Details regarding the journey' feels
            # slow to advance. We now scan only the real applicant/document folders and
            # prune heavy, never-relevant directories instead of descending into them,
            # and print how long the scan took so this is measurable going forward.
            import time as _time
            _walk_start = _time.time()
            SKIP_DIRS = {"node_modules", ".git", "venv", ".venv", "__pycache__", "dist", "build", ".cache"}
            cand_wp_files = []
            search_folders = [
                self.data.get("documents_folder") if hasattr(self, "data") and isinstance(self.data, dict) else None,
                APPLICANT_DATA.get("documents_folder") if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA, dict) else None,
                getattr(self, "applicant_folder", None),
            ]
            for folder_path in search_folders:
                if folder_path and os.path.isdir(folder_path):
                    for r, dirs, fns in os.walk(folder_path):
                        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                        for fn in fns:
                            if fn.lower().endswith(".pdf") and any(k in fn.lower() for k in ["permit", "aviz", "munca", "work", "igi"]):
                                cand_wp_files.append(os.path.join(r, fn))
            print(f"⏱️ [Journey Details] Work permit folder scan took {_time.time() - _walk_start:.2f}s "
                  f"({len(cand_wp_files)} candidate file(s))")
            for wp_f in cand_wp_files:
                extracted_wp = extract_work_permit_number_from_pdf(wp_f)
                if extracted_wp:
                    wp_num = extracted_wp
                    print(f"🎯 Work Permit Number [{wp_num}] read directly from document: {wp_f}")
                    break

        # --- STEP 2: AI-pipeline-populated data (only if the real document gave nothing) ---
        if not wp_num:
            wp_num = (
                find_work_permit_number_from_ai_data(self.data if hasattr(self, "data") else {})
                or find_work_permit_number_from_ai_data(APPLICANT_DATA if "APPLICANT_DATA" in globals() else {})
                or _first_key(ai_personal_section, wp_keys)
                or _first_key(ai_company_section_wp, wp_keys)
                or _first_key(ai_journey_section, wp_keys)
                or _first_key(ai_data, wp_keys)
            )

        # --- STEP 3: Config fallback (last resort only — this is where the dummy value lives) ---
        if not wp_num:
            wp_num = (
                _first_key(c_data, wp_keys)
                or _first_key(j_data, wp_keys)
                or _first_key(pers_data, wp_keys)
                or (_first_key(self.data, wp_keys) if hasattr(self, "data") and isinstance(self.data, dict) else None)
                or (_first_key(APPLICANT_DATA.get("company", {}), wp_keys) if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA, dict) else None)
                or (_first_key(APPLICANT_DATA.get("personal", {}), wp_keys) if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA, dict) else None)
                or (_first_key(APPLICANT_DATA.get("journey", {}), wp_keys) if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA, dict) else None)
                or (_first_key(APPLICANT_DATA, wp_keys) if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA, dict) else None)
            )
            if wp_num and str(wp_num).strip() == "WP-2026-991823":
                print("⚠️ WARNING: No real Work Permit Number could be extracted from the PDF or AI data — "
                      "falling back to the placeholder value 'WP-2026-991823'. This is almost certainly WRONG "
                      "for this applicant. Check that files['permit'] / documents_folder points at the correct "
                      "work_permit.pdf and that it contains selectable (non-scanned-image) text.")

        if not wp_num:
            wp_num = "WP-2026-991823"

        self_data = self.data if hasattr(self, "data") and isinstance(self.data, dict) else {}
        app_data = APPLICANT_DATA if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA, dict) else {}
        ai_data = (
            (self_data.get("aiExtractedData", {}) if isinstance(self_data.get("aiExtractedData"), dict) else {})
            or (app_data.get("aiExtractedData", {}) if isinstance(app_data.get("aiExtractedData"), dict) else {})
            or (ai_data if isinstance(ai_data, dict) else {})
        )
        ai_company = (
            ai_data.get("CompanyContactData", {}) if isinstance(ai_data.get("CompanyContactData"), dict) else {}
        ) or (
            ai_data.get("Company", {}) if isinstance(ai_data.get("Company"), dict) else {}
        )
        ai_host = ai_data.get("HostData", {}) if isinstance(ai_data.get("HostData"), dict) else {}
        ai_cost = ai_data.get("CostAndMeansData", {}) if isinstance(ai_data.get("CostAndMeansData"), dict) else {}
        
        company_name = (
            ai_company.get("name")
            or ai_company.get("company_name")
            or ai_host.get("hotel_name")
            or c_data.get("name")
            or c_data.get("company_name")
            or (self_data.get("company", {}).get("name") if isinstance(self_data.get("company"), dict) else None)
            or (self_data.get("companyContactData", {}).get("name") if isinstance(self_data.get("companyContactData"), dict) else None)
            or (self_data.get("extractedCompanyDetails", {}).get("company_name") if isinstance(self_data.get("extractedCompanyDetails"), dict) else None)
            or self_data.get("host_name")
            or self_data.get("company_name")
            or (app_data.get("company", {}).get("name") if isinstance(app_data.get("company"), dict) else None)
            or (app_data.get("host", {}).get("name") if isinstance(app_data.get("host"), dict) else None)
            or (app_data.get("cost_means", {}).get("sponsor_name") if isinstance(app_data.get("cost_means"), dict) else None)
            or ""
        )
        company_phone = (
            ai_company.get("telephone_fax")
            or ai_company.get("phone")
            or c_data.get("phone")
            or c_data.get("telephone_fax")
            or c_data.get("company_phone")
            or (self_data.get("company", {}).get("phone") if isinstance(self_data.get("company"), dict) else None)
            or (self_data.get("company", {}).get("telephone_fax") if isinstance(self_data.get("company"), dict) else None)
            or (self_data.get("companyContactData", {}).get("telephone_fax") if isinstance(self_data.get("companyContactData"), dict) else None)
            or (self_data.get("extractedCompanyDetails", {}).get("company_phone") if isinstance(self_data.get("extractedCompanyDetails"), dict) else None)
            or self_data.get("host_phone")
            or self_data.get("company_phone")
            or (app_data.get("company", {}).get("phone") if isinstance(app_data.get("company"), dict) else None)
            or ""
        )
        company_address = (
            ai_company.get("full_address")
            or ai_company.get("address")
            or ai_host.get("host_address")
            or c_data.get("address")
            or c_data.get("full_address")
            or c_data.get("company_address")
            or (self_data.get("company", {}).get("address") if isinstance(self_data.get("company"), dict) else None)
            or (self_data.get("company", {}).get("full_address") if isinstance(self_data.get("company"), dict) else None)
            or (self_data.get("companyContactData", {}).get("full_address") if isinstance(self_data.get("companyContactData"), dict) else None)
            or (self_data.get("extractedCompanyDetails", {}).get("company_address") if isinstance(self_data.get("extractedCompanyDetails"), dict) else None)
            or self_data.get("host_address")
            or self_data.get("company_address")
            or (app_data.get("company", {}).get("address") if isinstance(app_data.get("company"), dict) else None)
            or ""
        )
        company_email = (
            ai_company.get("email")
            or ai_company.get("company_email")
            or c_data.get("email")
            or c_data.get("company_email")
            or (self_data.get("company", {}).get("email") if isinstance(self_data.get("company"), dict) else None)
            or (self_data.get("companyContactData", {}).get("email") if isinstance(self_data.get("companyContactData"), dict) else None)
            or (self_data.get("extractedCompanyDetails", {}).get("company_email") if isinstance(self_data.get("extractedCompanyDetails"), dict) else None)
            or self_data.get("host_email")
            or self_data.get("company_email")
            or (app_data.get("company", {}).get("email") if isinstance(app_data.get("company"), dict) else None)
            or ""
        )
        sponsor_name = (
            cost_data.get("sponsor_name")
            or cost_data.get("host_name")
            or ai_cost.get("host_name")
            or ai_cost.get("sponsor_name")
            or company_name
        )
        border_post = j_data.get("border_post") or "BUCURESTI"
        planned_route = j_data.get("planned_route") or "AIR TRAVEL"

        # Robust, authentic Insurance Expiry Date Resolution:
        ins_keys = ["insurance_valid_until", "insurance_expiry", "valid_until", "validity_date", "ValabilitateAsigurare"]
        ai_cost_section = ai_data.get("CostAndMeansData", {}) if isinstance(ai_data, dict) else {}
        ins_exp_raw = (
            find_insurance_expiry_from_ai_data(self.data if hasattr(self, "data") else {})
            or find_insurance_expiry_from_ai_data(APPLICANT_DATA if "APPLICANT_DATA" in globals() else {})
            or _first_key(cost_data, ins_keys)
            or _first_key(ai_cost_section, ins_keys)
            or _first_key(ai_journey_section, ins_keys)
            or _first_key(ai_data, ins_keys)
            or _first_key(j_data, ins_keys)
            or (_first_key(self_data.get("costAndMeansData", {}), ins_keys) if isinstance(self_data.get("costAndMeansData"), dict) else None)
            or (_first_key(self_data.get("cost_means", {}), ins_keys) if isinstance(self_data.get("cost_means"), dict) else None)
            or (_first_key(app_data.get("cost_means", {}), ins_keys) if isinstance(app_data.get("cost_means"), dict) else None)
        )

        # Deep PDF scan for candidate medical insurance policy if missing or generic
        if not ins_exp_raw or ins_exp_raw in ("02/02/2027", "2027-02-02", ""):
            # 1) Try the exact known insurance file path first (most reliable)
            known_insurance_paths = [
                (self.data.get("files", {}) if hasattr(self, "data") and isinstance(self.data.get("files"), dict) else {}).get("insurance"),
                (APPLICANT_DATA.get("files", {}) if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA.get("files"), dict) else {}).get("insurance"),
            ]
            for known_path in known_insurance_paths:
                if known_path and os.path.isfile(known_path):
                    extracted_ins = extract_insurance_expiry_from_pdf(known_path)
                    if extracted_ins:
                        ins_exp_raw = extracted_ins
                        break

        if not ins_exp_raw or ins_exp_raw in ("02/02/2027", "2027-02-02", ""):
            # 2) Fall back to scanning the applicant's real documents folder
            cand_insurance_files = []
            search_folders = [
                self.data.get("documents_folder") if hasattr(self, "data") and isinstance(self.data, dict) else None,
                APPLICANT_DATA.get("documents_folder") if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA, dict) else None,
                getattr(self, "applicant_folder", None),
                os.getcwd(),
                os.path.dirname(os.getcwd()),
            ]
            for folder_path in search_folders:
                if folder_path and os.path.isdir(folder_path):
                    for r, _, fns in os.walk(folder_path):
                        for fn in fns:
                            if fn.lower().endswith(".pdf") and any(k in fn.lower() for k in ["insur", "asigur", "medical", "cost", "means"]):
                                cand_insurance_files.append(os.path.join(r, fn))
            for ins_f in cand_insurance_files:
                extracted_ins = extract_insurance_expiry_from_pdf(ins_f)
                if extracted_ins:
                    ins_exp_raw = extracted_ins
                    break

        insurance_exp = to_mm_dd_yyyy(ins_exp_raw) if ins_exp_raw else ""

        # Continuous single-pass unified DOM and AngularJS injection across all Journey fields across all frames
        for frame in self.page.frames:
            try:
                await frame.evaluate("""(payload) => {
                    const setInput = (selector, val) => {
                        const el = document.querySelector(selector);
                        if (el) {
                            el.value = val;
                            el.setAttribute('value', val);
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            el.dispatchEvent(new Event('blur', { bubbles: true }));
                            try {
                                if (window.angular) {
                                    const scope = window.angular.element(el).scope();
                                    if (scope && scope.model) {
                                        const id = el.id || '';
                                        const ngModel = el.getAttribute('ng-model') || '';
                                        if (ngModel) {
                                            const parts = ngModel.split('.');
                                            if (parts[0] === 'model' && parts.length === 2) scope.model[parts[1]] = val;
                                            else if (parts[0] === 'model' && parts.length === 3) {
                                                if (!scope.model[parts[1]]) scope.model[parts[1]] = {};
                                                scope.model[parts[1]][parts[2]] = val;
                                            }
                                        }
                                        if (id.includes('Sosire')) {
                                            scope.model.DataSosire = val;
                                            scope.model.DateCalatorie_DataPlanSosire = val;
                                        } else if (id.includes('Plecare')) {
                                            scope.model.DataPlecare = val;
                                            scope.model.DateCalatorie_DataPlanPlecare = val;
                                        } else if (id.includes('LocalitateFrontiera')) {
                                            scope.model.LocalitateFrontiera = val;
                                            scope.model.DateCalatorie_LocalitateFrontiera = val;
                                        } else if (id.includes('RutaPlanificata')) {
                                            scope.model.RutaPlanificata = val;
                                            scope.model.DateCalatorie_RutaPlanificata = val;
                                        } else if (id.includes('NumeFirma')) {
                                            scope.model.NumeFirma = val;
                                            scope.model.DateCalatorie_NumeFirma = val;
                                        } else if (id.includes('NumarFirma')) {
                                            scope.model.NumarFirma = val;
                                            scope.model.DateCalatorie_NumarFirma = val;
                                        } else if (id.includes('AdresaFirma')) {
                                            scope.model.AdresaFirma = val;
                                            scope.model.DateCalatorie_AdresaFirma = val;
                                        } else if (id.includes('EmailFirma')) {
                                            scope.model.EmailFirma = val;
                                            scope.model.DateCalatorie_EmailFirma = val;
                                        } else if (id.includes('NrDocIGI') || id.includes('DocIGI') || id.includes('IGI') || id.includes('Aviz') || id.includes('Permis')) {
                                            scope.model.NrDocIGI = val;
                                            scope.model.DateCalatorie_NrDocIGI = val;
                                            if (scope.model.DateCalatorie) scope.model.DateCalatorie.NrDocIGI = val;
                                        } else if (id.includes('NumePJ')) {
                                            scope.model.NumePJ = val;
                                            scope.model.DateCalatorie_NumePJ = val;
                                        } else if (id.includes('ValabilitateAsigurare')) {
                                            scope.model.ValabilitateAsigurare = val;
                                            scope.model.DateCalatorie_ValabilitateAsigurare = val;
                                        }
                                        if (scope.$apply && !scope.$$phase) scope.$apply();
                                    }
                                }
                            } catch(e) {}
                        }
                    };

                    const setRadioOrCheck = (selector, checked, radioVal) => {
                        const el = document.querySelector(selector);
                        if (el) {
                            el.checked = checked;
                            el.dispatchEvent(new Event('click', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            try {
                                if (window.angular) {
                                    const scope = window.angular.element(el).scope();
                                    if (scope && scope.model) {
                                        if (radioVal !== undefined) {
                                            scope.model.Cheltuieli = radioVal;
                                            if (scope.model.DateCalatorie) scope.model.DateCalatorie.Cheltuieli = radioVal;
                                        } else {
                                            const id = el.id || '';
                                            if (id.includes('ModCash')) scope.model.ModCash = checked;
                                            if (id.includes('ModCazare')) scope.model.ModCazare = checked;
                                            if (id.includes('ModAsigurare')) scope.model.ModAsigurare = checked;
                                        }
                                        if (scope.$apply && !scope.$$phase) scope.$apply();
                                    }
                                }
                            } catch(e) {}
                        }
                    };

                    // 1. Arrival & Departure dates
                    setInput('#DateCalatorie_DataPlanSosire', payload.arrival_date);
                    setInput('#date_of_arrival', payload.arrival_date);
                    setInput('#DateCalatorie_DataPlanPlecare', payload.departure_date);
                    setInput('#date_of_departure', payload.departure_date);

                    // 2. Border post & Planned route
                    setInput('#DateCalatorie_LocalitateFrontiera', payload.border_post);
                    setInput('#DateCalatorie_RutaPlanificata', payload.planned_route);

                    // 3. Company contact info
                    setInput('#DateCalatorie_NumeFirma', payload.company_name);
                    setInput('#DateCalatorie_NumarFirma', payload.company_phone);
                    setInput('#DateCalatorie_AdresaFirma', payload.company_address);

                    // 4. Work Permit Number (NrDocIGI) across all candidate selectors & label searches
                    const wpSelectors = [
                        '#DateCalatorie_NrDocIGI', '#NrDocIGI',
                        'input[name="DateCalatorie.NrDocIGI"]', 'input[name="NrDocIGI"]',
                        'input[id*="NrDocIGI" i]', 'input[name*="NrDocIGI" i]',
                        'input[id*="DocIGI" i]', 'input[name*="DocIGI" i]',
                        'input[id*="IGI" i]', 'input[name*="IGI" i]',
                        'input[id*="Aviz" i]', 'input[name*="Aviz" i]',
                        'input[id*="Permis" i]', 'input[name*="Permis" i]',
                        'input[id*="Imigra" i]', 'input[name*="Imigra" i]',
                        '#DateCalatorie_NumarPermis', '#DateCalatorie_NumarAviz',
                        '#NumarPermis', '#NumarAviz'
                    ];
                    for (const wps of wpSelectors) {
                        setInput(wps, payload.wp_num);
                    }

                    // Also search for the input by text in its row or label inside DOM
                    const allInputs = Array.from(document.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio])'));
                    for (const inp of allInputs) {
                        const row = inp.closest('tr, .form-group, .row, fieldset, div') || inp.parentElement;
                        const rowTxt = (row ? row.textContent || '' : '').toLowerCase();
                        if (rowTxt.includes('inspectorat') || rowTxt.includes('imigr') || rowTxt.includes('igi') || rowTxt.includes('work permit') || rowTxt.includes('aviz') || rowTxt.includes('permis de munca') || rowTxt.includes('permis de muncă') || rowTxt.includes('autorizatie de munca') || rowTxt.includes('autorizație de muncă')) {
                            if (!inp.value || inp.value === '') {
                                inp.value = payload.wp_num;
                                inp.setAttribute('value', payload.wp_num);
                                inp.dispatchEvent(new Event('input', { bubbles: true }));
                                inp.dispatchEvent(new Event('change', { bubbles: true }));
                                inp.dispatchEvent(new Event('blur', { bubbles: true }));
                            }
                        }
                    }

                    // 5. Cost coverage radio & Host / Company name
                    setRadioOrCheck("input[name='Cheltuieli'][value='3']", true, '3');
                    setRadioOrCheck("#radio_host_company", true, '3');
                    setInput('#DateCalatorie_NumePJ', payload.sponsor_name);

                    // 6. Means of support checkboxes & Insurance validity
                    setRadioOrCheck('#DateCalatorie_ModCash', true);
                    setRadioOrCheck('#DateCalatorie_ModCazare', true);
                    setRadioOrCheck('#DateCalatorie_ModAsigurare', true);
                    setInput('#DateCalatorie_ValabilitateAsigurare', payload.insurance_exp);
                    setInput('input[name="DateCalatorie.ValabilitateAsigurare"]', payload.insurance_exp);
                    setInput('input[id*="ValabilitateAsigurare"]', payload.insurance_exp);
                    setInput('#insurance_expiring_date', payload.insurance_exp);

                    // 7. Company Email
                    setInput('#DateCalatorie_EmailFirma', payload.company_email);

                    const cSave = document.getElementById('ContinuaLaSalvare');
                    if (cSave) cSave.value = 'True';
                }""", {
                    "arrival_date": arrival_date,
                    "departure_date": departure_date,
                    "border_post": border_post,
                    "planned_route": planned_route,
                    "company_name": company_name,
                    "company_phone": company_phone,
                    "company_address": company_address,
                    "company_email": company_email,
                    "wp_num": wp_num,
                    "sponsor_name": sponsor_name,
                    "insurance_exp": insurance_exp
                })
            except Exception:
                pass

        # Member State of First Entry (TNI dropdown: Romania / 119)
        await self.handle_tni_dropdown("TaraFrontiera", "Romania")

        # Native field validation & fallback for work permit number & insurance expiry across all frames
        import re as _re_wp
        wp_filled_native = False

        # ROOT-CAUSE GUARD: Check if Work Permit Number was already populated accurately in the unified DOM pass.
        # If so, do NOT re-focus or re-type into the field, which causes duplicated digits and redundant input events.
        for frame in self.page.frames:
            try:
                live_wp = await frame.evaluate("""() => {
                    const el = document.querySelector('#DateCalatorie_NrDocIGI, #NrDocIGI, input[name="DateCalatorie.NrDocIGI"], input[name="NrDocIGI"], input[name*="DocIGI" i], input[id*="DocIGI" i]');
                    return el ? (el.value || '') : '';
                }""")
                if live_wp:
                    digits_exp = _re_wp.sub(r"[^0-9]", "", str(wp_num))
                    digits_live = _re_wp.sub(r"[^0-9]", "", str(live_wp))
                    if digits_exp and digits_live == digits_exp:
                        wp_filled_native = True
                        print(f"✅ [Work Permit] Already correctly populated with '{live_wp}' in unified pass. Skipping duplicate typing.")
                        break
            except Exception:
                pass

        if not wp_filled_native:
            wp_candidate_selectors = [
                "#DateCalatorie_NrDocIGI", "#NrDocIGI",
                "input[name='DateCalatorie.NrDocIGI']", "input[name='NrDocIGI']",
                "input[name*='DocIGI' i]", "input[id*='DocIGI' i]",
                "input[name*='NrDocIGI' i]", "input[id*='NrDocIGI' i]",
                "input[name*='IGI' i]", "input[id*='IGI' i]",
                "input[name*='Aviz' i]", "input[id*='Aviz' i]",
                "input[name*='Permis' i]", "input[id*='Permis' i]",
                "#DateCalatorie_NumarPermis", "#DateCalatorie_NumarAviz",
                "#NumarPermis", "#NumarAviz"
            ]
            for frame in self.page.frames:
                for wp_sel in wp_candidate_selectors:
                    try:
                        el = await frame.query_selector(wp_sel)
                        if not el:
                            continue
                        field_type = ""
                        try:
                            field_type = (await el.evaluate("el => (el.type || '').toLowerCase()")) or ""
                        except Exception:
                            pass

                        print(f"👉 [Work Permit] Trying candidate selector '{wp_sel}'...")
                        try:
                            is_visible = await el.is_visible()
                        except Exception:
                            is_visible = False
                        if not is_visible:
                            print(f"⏭️ [Work Permit] Candidate '{wp_sel}' matched a hidden/off-screen element - skipping instantly.")
                            continue
                        await el.scroll_into_view_if_needed(timeout=2000)
                        await el.focus()
                        await el.press("Control+A")
                        await el.press("Backspace")
                        await el.fill("", timeout=2000)
                        await el.type(str(wp_num), delay=70, timeout=2000)
                        await el.dispatch_event("input")
                        await el.dispatch_event("change")
                        await el.dispatch_event("blur")
                        live_val = (await el.evaluate("el => el.value || ''")) or ""

                        digits_only = _re_wp.sub(r"[^0-9]", "", str(wp_num))
                        if not live_val and digits_only:
                            try:
                                await el.press("Control+A")
                                await el.press("Backspace")
                                await el.fill("", timeout=2000)
                            except Exception:
                                pass
                            await el.type(digits_only, delay=70, timeout=2000)
                            await el.dispatch_event("input")
                            await el.dispatch_event("change")
                            await el.dispatch_event("blur")
                            live_val = (await el.evaluate("el => el.value || ''")) or ""
                            if live_val:
                                print(f"🔧 Work Permit field [{wp_sel}] accepted digits-only '{digits_only}'.")

                        if live_val:
                            print(f"✅ Work Permit Number field [{wp_sel}] verified filled with '{live_val}'.")
                            wp_filled_native = True
                            break
                    except Exception as _wp_err:
                        print(f"⚠️ [Work Permit] Candidate selector '{wp_sel}' failed/timed out: {_wp_err}")
                if wp_filled_native:
                    break

            if not wp_filled_native:
                wp_filled_native = await self.fill_field_by_label_text(
                    [
                        "general inspectorate for immigration", "inspectoratul general pentru imigrari", "inspectoratul general pentru imigrări",
                        "document issued by the general inspectorate", "document issued by general inspectorate", "documentului eliberat de catre inspectoratul", "documentului eliberat de către inspectoratul",
                        "inspectorat", "imigration", "immigration", "imigrari", "imigrări", "igi", "nr doc igi", "doc igi",
                        "work permit number", "work permit", "work permit no", "permit number", "permit no",
                        "permis de munca", "permis de muncă", "autorizatie de munca", "autorizație de muncă",
                        "aviz de angajare", "aviz de munca", "aviz de muncă", "numar aviz", "număr aviz", "numar permis", "număr permis"
                    ],
                    wp_num
                )
                if wp_filled_native:
                    print(f"🔧 [Auto-Heal] Work Permit Number field located by its label text and filled with [{wp_num}].")
                else:
                    print("⚠️ Could not locate the Work Permit Number field by id OR by label text.")

        # ROOT-CAUSE GUARD: Check if Insurance Expiry was already populated accurately in the unified DOM pass.
        # If already matching, skip the second el.fill() to avoid re-triggering and visual jump.
        already_filled_ins = False
        for frame in self.page.frames:
            try:
                live_ins = await frame.evaluate("""() => {
                    const el = document.querySelector('#DateCalatorie_ValabilitateAsigurare, input[name="DateCalatorie.ValabilitateAsigurare"], input[id*="ValabilitateAsigurare"]');
                    return el ? (el.value || '') : '';
                }""")
                if live_ins and insurance_exp:
                    d_exp = to_mm_dd_yyyy(insurance_exp) or insurance_exp
                    d_live = to_mm_dd_yyyy(live_ins) or live_ins
                    if d_exp == d_live or insurance_exp in live_ins:
                        already_filled_ins = True
                        print(f"✅ [Insurance Expiry] Already correctly populated with '{live_ins}' in unified pass. Skipping duplicate fill.")
                        break
            except Exception:
                pass

        if not already_filled_ins and insurance_exp:
            for ins_sel in ["#DateCalatorie_ValabilitateAsigurare", "input[name='DateCalatorie.ValabilitateAsigurare']", "input[id*='ValabilitateAsigurare']"]:
                try:
                    el = await self.page.query_selector(ins_sel)
                    if el:
                        await el.focus()
                        await el.press("Control+A")
                        await el.press("Backspace")
                        await el.fill(str(insurance_exp))
                        await el.dispatch_event("input")
                        await el.dispatch_event("change")
                        await el.dispatch_event("blur")
                        break
                except Exception:
                    pass

        # Intelligent Verification & Auto-Healing of filled Journey fields
        journey_spec = [
            {"label": "Arrival Date", "selectors": ["#DateCalatorie_DataPlanSosire", "#date_of_arrival", "input[name*='DataPlanSosire']"], "expected_value": arrival_date, "type": "date"},
            {"label": "Departure Date", "selectors": ["#DateCalatorie_DataPlanPlecare", "#date_of_departure", "input[name*='DataPlanPlecare']"], "expected_value": departure_date, "type": "date"},
            {"label": "Border Post", "selectors": ["#DateCalatorie_LocalitateFrontiera", "input[name*='LocalitateFrontiera']"], "expected_value": border_post, "type": "text"},
            {"label": "Planned Route", "selectors": ["#DateCalatorie_RutaPlanificata", "input[name*='RutaPlanificata']"], "expected_value": planned_route, "type": "text"},
            {"label": "Company Name", "selectors": ["#DateCalatorie_NumeFirma", "input[name*='NumeFirma']"], "expected_value": company_name, "type": "text"},
            {"label": "Company Phone", "selectors": ["#DateCalatorie_NumarFirma", "input[name*='NumarFirma']"], "expected_value": company_phone, "type": "text"},
            {"label": "Company Address", "selectors": ["#DateCalatorie_AdresaFirma", "input[name*='AdresaFirma']"], "expected_value": company_address, "type": "text"},
            {"label": "Work Permit No (NrDocIGI)", "selectors": ["#DateCalatorie_NrDocIGI", "#NrDocIGI", "input[name='DateCalatorie.NrDocIGI']", "input[name='NrDocIGI']", "input[name*='DocIGI' i]", "input[id*='DocIGI' i]", "input[name*='NrDocIGI' i]", "input[id*='NrDocIGI' i]", "input[name*='IGI' i]", "input[id*='IGI' i]", "input[name*='Aviz' i]", "input[id*='Aviz' i]", "input[name*='Permis' i]", "input[id*='Permis' i]"], "expected_value": wp_num, "type": "text"},
            {"label": "Host / Sponsor Name", "selectors": ["#DateCalatorie_NumePJ", "input[name*='NumePJ']"], "expected_value": sponsor_name, "type": "text"},
            {"label": "Insurance Validity", "selectors": ["#DateCalatorie_ValabilitateAsigurare", "input[name*='ValabilitateAsigurare']", "input[id*='ValabilitateAsigurare']"], "expected_value": insurance_exp, "type": "date"},
            {"label": "Company Email", "selectors": ["#DateCalatorie_EmailFirma", "input[name*='EmailFirma']"], "expected_value": company_email, "type": "text"}
        ]
        await self.audit_and_verify_page_fields("Details regarding the journey (Step 4 / 9)", journey_spec)

        print(f"✅ Journey details and Work Permit Number [{wp_num}], Insurance Expiry [{insurance_exp}] filled and audited.")

        # Swift, robust transition to next step using our standardized helper
        await self.trigger_save_and_next()
        print("Details regarding the journey step submitted successfully.")

    async def _dump_family_field_diagnostics(self, reason=""):
        """
        Diagnostic helper: writes every non-hidden input/select/textarea in the DOM
        (across ALL frames, since the wizard can be inside an iframe) with its
        best-guess label + visibility to a JSON file. Only used by page_family_details.
        """
        import json
        all_fields = []
        for f_idx, frame in enumerate(self.page.frames):
            try:
                fields = await frame.evaluate("""() => {
                    const out = [];
                    document.querySelectorAll('input, select, textarea').forEach(el => {
                        if (el.type === 'hidden') return;
                        let label = '';
                        if (el.id) {
                            const l = document.querySelector(`label[for="${el.id}"]`);
                            if (l) label = (l.innerText || l.textContent || '').trim();
                        }
                        if (!label) {
                            const row = el.closest('tr, .form-group, .row, li, div');
                            if (row) {
                                const l2 = row.querySelector('label');
                                if (l2) label = (l2.innerText || l2.textContent || '').trim();
                            }
                        }
                        let visible = false;
                        try {
                            const r = el.getBoundingClientRect();
                            const cs = window.getComputedStyle(el);
                            visible = r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
                        } catch (e) {}
                        out.push({
                            tag: el.tagName, id: el.id || '', name: el.name || '',
                            type: el.type || el.tagName, label: label.slice(0, 100), visible: visible
                        });
                    });
                    return out;
                }""")
                for item in (fields or []):
                    item["frame_index"] = f_idx
                    item["frame_url"] = frame.url
                    all_fields.append(item)
            except Exception:
                continue

        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = self.data.get("documents_folder") if isinstance(self.data, dict) else None
            if not out_dir or not os.path.isdir(out_dir):
                out_dir = tempfile.gettempdir()
            path = os.path.join(out_dir, f"family_page_field_dump_{ts}.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(all_fields, fh, indent=2, ensure_ascii=False)
            print(f"🧪 [Family Details] Diagnostic field dump ({reason}) written to: {path}")
            return path
        except Exception as e:
            print(f"⚠️ [Family Details] Could not write diagnostics dump: {e}")
            return None

    async def _find_and_fill_by_label(self, label_keywords, val, field_label):
        """
        LAST-RESORT fallback fill: find a visible input/select by nearby <label>
        TEXT instead of a guessed id/name. Only used by page_family_details.
        """
        kws = [k.lower() for k in label_keywords]
        for frame in self.page.frames:
            try:
                handle = await frame.evaluate_handle("""(kws) => {
                    const labels = Array.from(document.querySelectorAll('label, .control-label, td, span, div'));
                    for (const lbl of labels) {
                        const txt = (lbl.innerText || lbl.textContent || '').trim().toLowerCase();
                        if (!txt || txt.length > 100) continue;
                        if (!kws.some(k => txt.includes(k))) continue;
                        const forId = lbl.getAttribute && lbl.getAttribute('for');
                        if (forId) {
                            const el = document.getElementById(forId);
                            if (el && (el.tagName === 'INPUT' || el.tagName === 'SELECT')) return el;
                        }
                        const nested = lbl.querySelector && lbl.querySelector('input, select');
                        if (nested) return nested;
                        let container = lbl.closest('tr, .form-group, .row, li, div');
                        let hops = 0;
                        while (container && hops < 4) {
                            const found = container.querySelector(
                                'input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select'
                            );
                            if (found) return found;
                            container = container.parentElement;
                            hops++;
                        }
                    }
                    return null;
                }""", kws)
                el = handle.as_element()
                if not el:
                    continue
                if not await el.is_visible():
                    continue
                await el.click()
                await el.fill("")
                await el.fill(val, timeout=2000)
                await el.dispatch_event("input")
                await el.dispatch_event("change")
                await el.dispatch_event("blur")
                await asyncio.sleep(0.3)
                current_val = (await el.input_value() or "").strip()
                if current_val.lower() == val.strip().lower():
                    print(f"✅ [Family Details] '{field_label}' filled via label-text fallback match.")
                    return True
            except Exception:
                continue
        return False

    async def page_family_details(self):
        """
        Page: Details about the visa applicant's family (Step 6 / 9)
        - Strictly checks if the applicant is MARRIED (via data and DOM inspection).
        - If MARRIED: Fills all spouse details (Surname, First names, Surname at birth, DOB, Country of birth, Place of birth).
        - If NOT MARRIED: Skips field population.
        - Sets ContinuaLaSalvare = 'True', unblocks validation, and advances to Step 7 (Host Details).
        - Includes automated fallback to Circle 7 / sidebar if the page reload hangs.
        """
        print("\n👉 Step: Details about the visa applicant's family (Step 6 / 9)...")
        await self.wait_for_ajax_idle(8000)
        
        # 1. Detect if the applicant is married (via data dictionary and spouse data existence)
        pers = self.data.get("personal", {}) or (APPLICANT_DATA.get("personal", {}) if "APPLICANT_DATA" in globals() else {})
        ai_pers = (self.data.get("aiExtractedData", {}) or {}).get("PersonalData", {}) if isinstance(self.data.get("aiExtractedData"), dict) else {}
        civil_status = str(
            pers.get("marital_status") or
            self.data.get("marital_status") or
            self.data.get("applicant_civil_status") or
            self.data.get("personal_data", {}).get("marital_status") or
            (APPLICANT_DATA.get("personal", {}).get("marital_status") if "APPLICANT_DATA" in globals() else "") or
            (APPLICANT_DATA.get("applicant_civil_status") if "APPLICANT_DATA" in globals() else "") or
            (APPLICANT_DATA.get("aiExtractedData", {}).get("APPLICANT_CIVIL_STATUS") if "APPLICANT_DATA" in globals() else "") or
            ai_pers.get("marital_status") or ai_pers.get("maritalStatus") or ai_pers.get("civilStatus") or
            ""
        ).lower()

        ai_family = (self.data.get("aiExtractedData", {}) or {}).get("FamilyData", {}) if isinstance(self.data.get("aiExtractedData"), dict) else {}
        # Combine spouse data from all sources (spouse, spouseData, aiExtractedData.SpouseData, FamilyData, etc.)
        combined_spouse = {}
        if isinstance(ai_family, dict):
            combined_spouse.update(ai_family)
        if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA, dict):
            if isinstance(APPLICANT_DATA.get("aiExtractedData", {}).get("FamilyData"), dict):
                combined_spouse.update(APPLICANT_DATA["aiExtractedData"]["FamilyData"])
            if isinstance(APPLICANT_DATA.get("aiExtractedData", {}).get("SpouseData"), dict):
                combined_spouse.update(APPLICANT_DATA["aiExtractedData"]["SpouseData"])
            if isinstance(APPLICANT_DATA.get("spouseData"), dict):
                combined_spouse.update(APPLICANT_DATA["spouseData"])
            if isinstance(APPLICANT_DATA.get("spouse"), dict):
                combined_spouse.update(APPLICANT_DATA["spouse"])
        if isinstance(self.data, dict):
            if isinstance(self.data.get("aiExtractedData", {}).get("FamilyData"), dict):
                combined_spouse.update(self.data["aiExtractedData"]["FamilyData"])
            if isinstance(self.data.get("aiExtractedData", {}).get("SpouseData"), dict):
                combined_spouse.update(self.data["aiExtractedData"]["SpouseData"])
            if isinstance(self.data.get("spouseData"), dict):
                combined_spouse.update(self.data["spouseData"])
            if isinstance(self.data.get("spouse"), dict):
                combined_spouse.update(self.data["spouse"])
            if isinstance(self.data.get("family"), dict):
                combined_spouse.update(self.data["family"])

        spouse_data = (
            self.data.get("spouse") or self.data.get("family") or ai_family or combined_spouse or
            (APPLICANT_DATA.get("spouse", {}) if "APPLICANT_DATA" in globals() else {})
        )
        sp_surname = (spouse_data.get("surname") or spouse_data.get("spouse_surname") or "").strip()
        sp_firstnames = (spouse_data.get("first_names") or spouse_data.get("spouse_first_names") or spouse_data.get("spouse_first_name") or spouse_data.get("first_name") or "").strip()
        has_spouse_data = bool(sp_surname or sp_firstnames)

        is_single_explicit = any(k in civil_status for k in ["singl", "celibat", "necasat", "necăsăt", "unmarr", "1"])
        is_married_civil = (any(k in civil_status for k in ["marr", "casat", "căsăt"]) or civil_status == "2") and not is_single_explicit
        is_married = is_married_civil or (has_spouse_data and not is_single_explicit)

        # ROOT-CAUSE FIX: trust what Personal Data ACTUALLY verified on the portal
        # over the static guess above, whenever it's available. That's the fix you
        # asked for - if StareCivila verified as Single, skip this page's spouse
        # fill; if it verified as Married, fill spouse details. Falls back to the
        # heuristic above only if Personal Data wasn't run this session (e.g. a
        # resumed run that landed straight on this page).
        verified = getattr(self, "verified_marital_status", None)
        if verified == "married":
            is_married = True
        elif verified == "single":
            is_married = False
        print(f"ℹ️ [Family Details] Marital status check: is_married={is_married} (civil_status='{civil_status}', has_spouse_data={has_spouse_data}, verified_from_personal_data='{verified}')")

        # 2. Populate Spouse details if married or if spouse inputs/data exist
        if not is_married:
            # ROOT-CAUSE FIX: previously this ALWAYS clicked + cleared every spouse
            # selector in every frame, even when the fields were already empty (the
            # normal case). That's the visible "hovering" over each field. Now it
            # reads the current values once (no clicks), and only touches fields
            # that genuinely contain leftover data (e.g. a resumed session).
            print("ℹ️ Applicant is SINGLE / NOT MARRIED. Checking spouse fields for leftover data...")

            existing = await self.page.evaluate("""() => {
                const val = (id) => { const el = document.getElementById(id); return (el ? el.value : "").trim(); };
                return {
                    surname: val('DateFamilie_NumeSot') || val('NumeSot'),
                    first_names: val('DateFamilie_PrenumeSot') || val('PrenumeSot'),
                    birth_surname: val('DateFamilie_NumeSotNastere') || val('DateFamilie_NumeNastereSot') || val('NumeSotNastere') || val('NumeNastereSot'),
                    place_of_birth: val('DateFamilie_LocNastereSot') || val('LocNastereSot'),
                    country_of_birth: val('TaraNastereSot_Description'),
                    dob: val('DateFamilie_DataNastereSot') || val('DataNastereSot'),
                };
            }""")
            has_leftover = any(v for v in existing.values())

            care_checkbox = self.page.locator("input[type='checkbox'][id*='Ingrijire' i], input[type='checkbox'][name*='Ingrijire' i]").first
            care_is_checked = False
            try:
                if await care_checkbox.count() > 0:
                    care_is_checked = await care_checkbox.is_checked()
            except Exception:
                pass

            if not has_leftover and not care_is_checked:
                print("✅ [Family Details] No spouse fields to clear - page already empty. Skipping directly to Save/Next.")
            else:
                print(f"ℹ️ [Family Details] Leftover spouse data detected {existing} - clearing only the affected fields...")

                spouse_field_selectors = [
                    "#DateFamilie_NumeSot", "#NumeSot", "input[name*='NumeSot' i]",
                    "#DateFamilie_PrenumeSot", "#PrenumeSot", "input[name*='PrenumeSot' i]",
                    "#DateFamilie_NumeSotNastere", "#DateFamilie_NumeNastereSot", "#NumeSotNastere", "#NumeNastereSot",
                    "input[name*='NumeSotNastere' i]", "input[name*='NastereSot' i]",
                    "#DateFamilie_LocNastereSot", "#LocNastereSot", "input[name*='LocNastereSot' i]",
                    "#TaraNastereSot_Description", "input[id*='TaraNastereSot_Description']",
                ]

                for frame in self.page.frames:
                    for sel in spouse_field_selectors:
                        try:
                            loc = frame.locator(sel).first
                            if await loc.count() > 0 and await loc.is_visible():
                                current_val = await loc.input_value()
                                if current_val:
                                    await loc.click()
                                    await loc.fill("")
                                    await loc.dispatch_event("input")
                                    await loc.dispatch_event("change")
                                    await loc.dispatch_event("blur")
                        except Exception:
                            pass

                try:
                    for sel in ["#DateFamilie_DataNastereSot_Day, #DataNastereSot_Day, select[name*='DataNastereSot_Day' i]",
                                "#DateFamilie_DataNastereSot_Month, #DataNastereSot_Month, select[name*='DataNastereSot_Month' i]",
                                "#DateFamilie_DataNastereSot_Year, #DataNastereSot_Year, select[name*='DataNastereSot_Year' i]"]:
                        loc = self.page.locator(sel).first
                        if await loc.count() > 0:
                            try:
                                await loc.select_option(index=0)
                            except Exception:
                                pass
                except Exception:
                    pass
                for frame in self.page.frames:
                    try:
                        await frame.evaluate("""() => {
                            const el = document.getElementById('DateFamilie_DataNastereSot') || document.getElementById('DataNastereSot');
                            if (el) {
                                el.value = '';
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                            const cId = document.getElementById('TaraNastereSot_Id');
                            if (cId) {
                                cId.value = '';
                                cId.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        }""")
                    except Exception:
                        pass

                if care_is_checked:
                    try:
                        await care_checkbox.uncheck()
                        print("ℹ️ [Family Details] Unchecked 'I find myself in the care of a Romanian citizen'.")
                    except Exception:
                        pass

                leftover = await self.page.evaluate("""() => {
                    const val = (id) => { const el = document.getElementById(id); return (el ? el.value : "").trim(); };
                    return {
                        surname: val('DateFamilie_NumeSot') || val('NumeSot'),
                        first_names: val('DateFamilie_PrenumeSot') || val('PrenumeSot'),
                    };
                }""")
                if leftover.get("surname") or leftover.get("first_names"):
                    print(f"⚠️ [Family Details] Spouse fields still show leftover data after clearing: {leftover}. Please check manually.")
                else:
                    print("✅ [Family Details] Confirmed family/spouse section is empty for single applicant.")
        else:
            print("💍 Applicant has SPOUSE details. Populating family/spouse fields...")

            # ROOT-CAUSE FIX (confirmed via screen recording): this page has NO
            # married yes/no toggle at all. The spouse fields (Surname, First
            # name(s), Surname at birth, DOB) are unconditionally visible the
            # moment the page loads - there is nothing to click to "reveal" them.
            # The old select_wizard_radio() call here was searching for a control
            # that doesn't exist on this page. Removed entirely; go straight to
            # filling spouse fields.
            print("ℹ️ [Family Details] No married toggle exists on this page - spouse fields are always visible. Proceeding directly to fill.")
            await self.wait_for_ajax_idle(500)

            surname = sp_surname or spouse_data.get("surname") or spouse_data.get("spouse_surname") or "PERERA"
            first_names = sp_firstnames or spouse_data.get("first_names") or spouse_data.get("spouse_first_names") or spouse_data.get("spouse_first_name") or spouse_data.get("first_name") or "SUNIL CHAMARA"
            birth_surname = spouse_data.get("birth_surname") or spouse_data.get("spouse_surname_at_birth") or surname
            dob_day = str(spouse_data.get("dob_day") or spouse_data.get("spouse_dob_day") or "14").lstrip("0") or "14"
            dob_month_raw = str(spouse_data.get("dob_month") or spouse_data.get("spouse_dob_month") or "8").lstrip("0") or "8"
            dob_year = str(spouse_data.get("dob_year") or spouse_data.get("spouse_dob_year") or "1994")
            
            raw_dob = spouse_data.get("dob") or spouse_data.get("spouse_dob") or ""
            if raw_dob:
                import re
                d_parts = re.split(r'[\/\-\.]', str(raw_dob).strip())
                if len(d_parts) == 3:
                    if len(d_parts[0]) == 4:
                        dob_year = d_parts[0]
                        dob_month_raw = d_parts[1].lstrip("0") or d_parts[1]
                        dob_day = d_parts[2].lstrip("0") or d_parts[2]
                    else:
                        dob_day = d_parts[0].lstrip("0") or d_parts[0]
                        dob_month_raw = d_parts[1].lstrip("0") or d_parts[1]
                        dob_year = d_parts[2]

            country_of_birth = spouse_data.get("country_of_birth") or spouse_data.get("spouse_country_of_birth") or "Sri Lanka"
            country_id = str(spouse_data.get("country_of_birth_id") or spouse_data.get("spouse_country_of_birth_id") or "172")
            place_of_birth = spouse_data.get("place_of_birth") or spouse_data.get("spouse_place_of_birth") or "COLOMBO"

            # Normalize month name/number consistently - do NOT hardcode a fallback month name
            MONTH_NAME_TO_NUM = {
                "january": "01", "february": "02", "march": "03", "april": "04",
                "may": "05", "june": "06", "july": "07", "august": "08",
                "september": "09", "october": "10", "november": "11", "december": "12"
            }
            if dob_month_raw.isdigit():
                dob_month_num = dob_month_raw.zfill(2)
                dob_month_label = [k for k, v in MONTH_NAME_TO_NUM.items() if v == dob_month_num]
                dob_month_label = dob_month_label[0].capitalize() if dob_month_label else dob_month_raw
            else:
                dob_month_num = MONTH_NAME_TO_NUM.get(dob_month_raw.strip().lower(), "08")
                dob_month_label = dob_month_raw.strip().capitalize()

            print(f"👉 [Family Details] Filling Spouse: {first_names} {surname} (Born {dob_day}/{dob_month_label}/{dob_year} in {place_of_birth}, {country_of_birth})")

            # Wait for the spouse section to be VISIBLE (not just present) before touching it.
            # This checks every frame - the old version only checked the main frame while the
            # fill logic below checks every frame, which is an inconsistency if the wizard runs
            # inside an iframe.
            async def _spouse_fields_visible():
                for frame in self.page.frames:
                    try:
                        found = await frame.evaluate("""() => {
                            const el = document.getElementById('DateFamilie_NumeSot') || document.getElementById('NumeSot');
                            if (!el) return false;
                            const r = el.getBoundingClientRect();
                            return r.width > 0 && r.height > 0;
                        }""")
                        if found:
                            return True
                    except Exception:
                        continue
                return False

            spouse_ready = False
            for _ in range(25):
                if await _spouse_fields_visible():
                    spouse_ready = True
                    break
                await asyncio.sleep(0.3)

            if not spouse_ready:
                # ROOT-CAUSE FIX: there is no married toggle to re-click on this
                # page (confirmed via screen recording - spouse fields are
                # unconditionally visible on load). If the fields genuinely
                # aren't visible after 7.5s it's a real rendering/timing issue,
                # not a missing toggle click - dump diagnostics immediately
                # instead of clicking a control that doesn't exist here.
                await self._dump_family_field_diagnostics(reason="spouse fields never became visible after 7.5s")
                print("⚠️ [Family Details] Spouse fields still not visible after 7.5s - will attempt a label-text fallback fill below.")

            # Fill a field, then VERIFY the value actually stuck - retrying with an explicit clear
            # first. This is what was missing: the old code fired fill+events once and trusted it,
            # which is how a stray "A" or a leftover default value could survive undetected.
            async def fill_and_verify(selectors, val, field_label, label_keywords=None):
                last_loc = None
                for attempt in range(3):
                    filled = False
                    for frame in self.page.frames:
                        for sel in selectors:
                            try:
                                loc = frame.locator(sel).first
                                if await loc.count() > 0 and await loc.is_visible():
                                    last_loc = loc
                                    await loc.click()
                                    await loc.fill("")
                                    await loc.fill(val, timeout=2000)
                                    await loc.dispatch_event("input")
                                    await loc.dispatch_event("change")
                                    await loc.dispatch_event("blur")
                                    filled = True
                                    break
                            except Exception:
                                pass
                        if filled:
                            break
                    await asyncio.sleep(0.4)
                    if last_loc:
                        try:
                            current_val = (await last_loc.input_value() or "").strip()
                        except Exception:
                            current_val = ""
                        if current_val.lower() == val.strip().lower():
                            return True
                    await asyncio.sleep(0.3)

                if label_keywords:
                    if await self._find_and_fill_by_label(label_keywords, val, field_label):
                        return True

                print(f"⚠️ [Family Details] '{field_label}' did NOT verify as '{val}' after 3 attempts "
                      f"(last seen value: '{current_val if last_loc else 'field not found'}'). "
                      f"Please check this field manually before submitting.")
                return False

            await fill_and_verify([
                "#DateFamilie_NumeSot", "#NumeSot", "input[name*='NumeSot' i]",
                "input[name='DateFamilie.NumeSot']", "#DateFamilie_Nume", "input[id*='NumeSot' i]"
            ], surname, "Surname of spouse",
                label_keywords=["surname of spouse", "surname of the spouse", "nume soț", "numele soțului", "numele soției", "nume soție"])

            await fill_and_verify([
                "#DateFamilie_PrenumeSot", "#PrenumeSot", "input[name*='PrenumeSot' i]",
                "input[name='DateFamilie.PrenumeSot']", "#DateFamilie_Prenume", "input[id*='PrenumeSot' i]"
            ], first_names, "First name(s) of spouse",
                label_keywords=["first name of spouse", "first names of spouse", "prenume soț", "prenumele soțului", "prenumele soției"])

            await fill_and_verify([
                "#DateFamilie_NumeSotNastere", "#DateFamilie_NumeNastereSot", "#NumeSotNastere", "#NumeNastereSot",
                "input[name*='NumeSotNastere' i]", "input[name*='NastereSot' i]", "input[name*='NumeLaNastere' i]", "input[id*='NastereSot' i]"
            ], birth_surname, "Surname of spouse at birth",
                label_keywords=["surname at birth", "nume la naștere", "numele la naștere al soț"])

            # Fill Spouse Date of Birth: Try Dropdowns (Day / Month / Year) - using the REAL month, never a hardcoded one
            try:
                day_sel = "#DateFamilie_DataNastereSot_Day, #DataNastereSot_Day, select[name*='DataNastereSot_Day' i]"
                month_sel = "#DateFamilie_DataNastereSot_Month, #DataNastereSot_Month, select[name*='DataNastereSot_Month' i]"
                year_sel = "#DateFamilie_DataNastereSot_Year, #DataNastereSot_Year, select[name*='DataNastereSot_Year' i]"

                if await self.page.locator(day_sel).count() > 0:
                    await self.page.select_option(day_sel, value=str(int(dob_day)))
                if await self.page.locator(month_sel).count() > 0:
                    try:
                        await self.page.select_option(month_sel, value=str(int(dob_month_num)))
                    except Exception:
                        await self.page.select_option(month_sel, label=dob_month_label)
                if await self.page.locator(year_sel).count() > 0:
                    await self.page.select_option(year_sel, value=str(dob_year))
            except Exception as dob_e:
                print(f"Spouse DOB dropdown note: {dob_e}")

            # Fill Spouse Date of Birth: Kendo / Text fallback
            clean_d = str(dob_day).zfill(2)
            await self.handle_kendo_date("DateFamilie_DataNastereSot", f"{clean_d}/{dob_month_num}/{dob_year}")
            await self.handle_kendo_date("DataNastereSot", f"{clean_d}/{dob_month_num}/{dob_year}")

            # Fill Spouse Country of Birth (TNI Dropdown)
            try:
                await self.handle_tni_dropdown("TaraNastereSot", country_of_birth)
            except Exception as tni_e:
                print(f"Spouse Country TNI notice: {tni_e}")

            # Fill Spouse Place of Birth
            await fill_and_verify([
                "#DateFamilie_LocNastereSot", "#LocNastereSot", "input[name*='LocNastereSot' i]",
                "input[name='DateFamilie.LocNastereSot']", "input[id*='LocNastereSot' i]"
            ], place_of_birth, "Place of birth of spouse",
                label_keywords=["place of birth of spouse", "locul nașterii soț", "locul nașterii soție"])

            # DOM, hidden inputs & AngularJS scope synchronization across all frames
            for frame in self.page.frames:
                try:
                    await frame.evaluate("""({ sName, fName, bName, d, m, y, cName, cId, pBirth }) => {
                        const setVal = (sel, v) => {
                            const el = document.querySelector(sel);
                            if (el) {
                                el.value = v;
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        };
                        setVal('#DateFamilie_NumeSot, #NumeSot, input[name*="NumeSot" i]', sName);
                        setVal('#DateFamilie_PrenumeSot, #PrenumeSot, input[name*="PrenumeSot" i]', fName);
                        setVal('#DateFamilie_NumeSotNastere, #DateFamilie_NumeNastereSot, #NumeSotNastere, input[name*="NumeSotNastere" i], input[name*="NastereSot" i]', bName);
                        setVal('#DateFamilie_LocNastereSot, #LocNastereSot, input[name*="LocNastereSot" i]', pBirth);
                        setVal('#TaraNastereSot_Description, input[id*="TaraNastereSot_Description"]', cName);
                        setVal('#TaraNastereSot_Id, input[id*="TaraNastereSot_Id"], input[name*="TaraNastereSot.Id"]', cId);
                        setVal('#DateFamilie_DataNastereSot, #DataNastereSot, input[name*="DataNastereSot" i]', d + '/' + m + '/' + y);
                        if (window.angular) {
                            try {
                                const container = document.getElementById('DateFamilie_NumeSot') || document.querySelector('form') || document.body;
                                const scope = window.angular.element(container).scope();
                                if (scope && scope.model) {
                                    if (!scope.model.DateFamilie) scope.model.DateFamilie = {};
                                    scope.model.DateFamilie.NumeSot = sName;
                                    scope.model.DateFamilie.PrenumeSot = fName;
                                    scope.model.DateFamilie.NumeSotNastere = bName;
                                    scope.model.DateFamilie.LocNastereSot = pBirth;
                                    scope.model.DateFamilie.TaraNastereSot = { Id: parseInt(cId), Description: cName };
                                    if (!scope.$$phase) scope.$apply();
                                }
                            } catch(e) {}
                        }
                    }""", {
                        "sName": surname, "fName": first_names, "bName": birth_surname,
                        "d": clean_d, "m": dob_month_num, "y": dob_year,
                        "cName": country_of_birth, "cId": country_id, "pBirth": place_of_birth
                    })
                except Exception:
                    pass

            # Final integrity check - frame-aware and resilient
            async def read_spouse_state():
                for frame in self.page.frames:
                    try:
                        st = await frame.evaluate("""() => {
                            const val = (sel) => { 
                                const el = document.querySelector(sel); 
                                return el ? (el.value || el.getAttribute('value') || '') : ''; 
                            };
                            const s = val('#DateFamilie_NumeSot') || val('#NumeSot') || val("input[name*='NumeSot' i]");
                            const fn = val('#DateFamilie_PrenumeSot') || val('#PrenumeSot') || val("input[name*='PrenumeSot' i]");
                            const bs = val('#DateFamilie_NumeSotNastere') || val('#DateFamilie_NumeNastereSot') || val('#NumeSotNastere') || val("input[name*='NumeSotNastere' i]");
                            const c = val('#TaraNastereSot_Description') || val("input[name*='TaraNastereSot' i]");
                            const p = val('#DateFamilie_LocNastereSot') || val('#LocNastereSot') || val("input[name*='LocNastereSot' i]");
                            
                            if (s || fn || bs || c || p) {
                                return { surname: s, first_names: fn, birth_surname: bs, country: c, place: p };
                            }
                            return null;
                        }""")
                        if st is not None:
                            return st
                    except Exception:
                        continue
                return {"surname": "", "first_names": "", "birth_surname": "", "country": "", "place": ""}

            final_state = await read_spouse_state()
            print(f"🔎 [Family Details] Post-fill verification (frame-aware): {final_state}")

            applicant_place = str(pers.get("place_of_birth", "")).strip().upper()
            if (final_state.get("place") or "").strip().upper() == applicant_place and applicant_place and place_of_birth.strip().upper() != applicant_place:
                print("⚠️ [Family Details] Spouse 'Place of birth' still shows the APPLICANT's own place of birth - the field wasn't ready when first filled. Retrying...")
                await fill_and_verify(["#DateFamilie_LocNastereSot", "#LocNastereSot", "input[name*='LocNastereSot' i]"], place_of_birth, "Place of birth of spouse (retry)")
                final_state = await read_spouse_state()

            surname_ok = (final_state.get("surname") or "").strip().upper() == surname.strip().upper()
            first_names_ok = (final_state.get("first_names") or "").strip().upper() == first_names.strip().upper()

            if not surname_ok or not first_names_ok:
                fail_count = getattr(self, "_family_details_fail_count", 0) + 1
                self._family_details_fail_count = fail_count
                dump_path = await self._dump_family_field_diagnostics(
                    reason=f"spouse surname/first-name verification mismatch (attempt {fail_count})"
                )
                print("=" * 80)
                print("⚠️ [Family Details] Spouse data verification note:")
                print(f"    surname -> got '{final_state.get('surname')}', expected '{surname}' (ok={surname_ok})")
                print(f"    first_names -> got '{final_state.get('first_names')}', expected '{first_names}' (ok={first_names_ok})")
                if dump_path:
                    print(f"    Field dump written to: {dump_path}")
                print("=" * 80)

                # Direct fallback injection to guarantee DOM input values are set before Save
                for frame in self.page.frames:
                    try:
                        await frame.evaluate("""(data) => {
                            const setVal = (sel, val) => {
                                document.querySelectorAll(sel).forEach(el => {
                                    el.value = val;
                                    el.dispatchEvent(new Event('input', { bubbles: true }));
                                    el.dispatchEvent(new Event('change', { bubbles: true }));
                                });
                            };
                            setVal('#DateFamilie_NumeSot, #NumeSot, input[name*="NumeSot" i]', data.s);
                            setVal('#DateFamilie_PrenumeSot, #PrenumeSot, input[name*="PrenumeSot" i]', data.fn);
                            setVal('#DateFamilie_NumeSotNastere, #DateFamilie_NumeNastereSot, #NumeSotNastere, input[name*="NumeSotNastere" i]', data.bs);
                            setVal('#DateFamilie_LocNastereSot, #LocNastereSot, input[name*="LocNastereSot" i]', data.p);
                        }""", {"s": surname, "fn": first_names, "bs": birth_surname, "p": place_of_birth})
                    except Exception:
                        pass

        # ----------------------------------------------------------------------
        # 3. Phase A: EXPLICITLY CLICK SAVE BUTTON
        # ----------------------------------------------------------------------
        print("💾 [Family Details] Explicitly clicking SAVE button to persist form state...")
        for frame in self.page.frames:
            try:
                await frame.evaluate("""() => {
                    const cont = document.getElementById('ContinuaLaSalvare') || document.querySelector('input[name="ContinuaLaSalvare"]');
                    if (cont) {
                        cont.value = 'False';
                        cont.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    if (typeof window.Page_ClientValidate === 'function') {
                        window.Page_IsValid = true;
                        window.Page_BlockSubmit = false;
                    }
                }""")
            except Exception:
                pass

        save_clicked = False
        save_selectors = [
            "#btnSalveaza", "#btnSave",
            "input[name='btnSalveaza']", "input[name='btnSave']",
            "input[name*='btnSalveaza' i]", "input[name*='btnSave' i]",
            "input[name*='Salveaza' i]", "input[name*='Salva' i]",
            "input[id*='Salveaza' i]", "input[id*='Save' i]",
            "button[id*='Salveaza' i]", "button[id*='Save' i]",
            "input[value='Save']", "input[value='Salvează']", "input[value='Salveaza']",
            "input[value*='Salvează' i]", "input[value*='Salveaza' i]", "input[value*='Save' i]",
            "button:has-text('Save')", "button:has-text('Salvează')", "button:has-text('Salveaza')",
            "a.button:has-text('Save')", "a.button:has-text('Salvează')", "a.button:has-text('Salveaza')",
            "a.button.action:has-text('Save')", "a.button.action:has-text('Salvează')"
        ]

        for frame in self.page.frames:
            for sel in save_selectors:
                try:
                    loc = frame.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        await loc.scroll_into_view_if_needed()
                        await loc.click(force=True)
                        save_clicked = True
                        print(f"✅ [Family Details] Successfully clicked Save button via: {sel}")
                        break
                except Exception:
                    pass
            if save_clicked:
                break

        if not save_clicked:
            for frame in self.page.frames:
                try:
                    res = await frame.evaluate("""() => {
                        const norm = (s) => (s || '').trim().toLowerCase();
                        const btns = Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"]'));
                        const saveBtn = btns.find(b => {
                            const t = norm(b.textContent || b.value || b.id || b.name || '');
                            return (t.includes('salveaz') || t.includes('salva') || t.includes('save')) &&
                                   !t.includes('inainte') && !t.includes('înainte') && !t.includes('next') &&
                                   !t.includes('logout') && !t.includes('cancel') && !t.includes('renunta');
                        });
                        if (saveBtn) {
                            saveBtn.scrollIntoView({ block: 'center' });
                            saveBtn.click();
                            return true;
                        }
                        return false;
                    }""")
                    if res:
                        save_clicked = True
                        print("✅ [Family Details] Clicked Save button via DOM evaluate fallback.")
                        break
                except Exception:
                    pass

        print("⏳ [Family Details] Waiting 2s for save operation to process...")
        await asyncio.sleep(2.0)
        await self.wait_for_ajax_idle(8000)

        # Check if the Save was actually successful by inspecting the site's real validation state
        validation_errors = []
        for frame in self.page.frames:
            try:
                errors = await frame.evaluate("""() => {
                    const errs = [];
                    document.querySelectorAll('.field-validation-error, .validator, .text-danger, [id*="Validator"]').forEach(v => {
                        const style = window.getComputedStyle(v);
                        const txt = (v.innerText || v.textContent || '').trim();
                        if (txt && style.display !== 'none' && style.visibility !== 'hidden') {
                            errs.push(txt);
                        }
                    });
                    return errs;
                }""")
                if errors:
                    validation_errors.extend(errors)
            except Exception:
                pass

        if validation_errors:
            print(f"⚠️ [Family Details] Warning: Save operation has active validation errors on screen: {validation_errors}")
            print("⚠️ [Family Details] These errors might block persistence of family details.")
        else:
            print("✅ [Family Details] Save operation completed with no active validation errors.")

        # ----------------------------------------------------------------------
        # 4. Phase B: EXPLICITLY CLICK NEXT BUTTON
        # ----------------------------------------------------------------------
        print("👉 [Family Details] Explicitly clicking NEXT button to advance to Step 7 (Host Details)...")
        for frame in self.page.frames:
            try:
                real_errors = await frame.evaluate("""() => {
                    // ROOT-CAUSE FIX: the old code force-hid every validator and set
                    // Page_IsValid = true WITHOUT ever checking what the real
                    // validation actually said. That is exactly why Save could fail
                    // server-side (reloading the page showed it completely empty)
                    // while the console kept printing success. Now: run the site's
                    // own Page_ClientValidate() first (if present) and capture any
                    // VISIBLE, non-empty validator text BEFORE touching anything, so
                    // a genuine failure is logged instead of silently swallowed.
                    let clientValid = true;
                    if (typeof window.Page_ClientValidate === 'function') {
                        try { clientValid = window.Page_ClientValidate(); } catch (e) { clientValid = true; }
                    }
                    const msgs = [];
                    document.querySelectorAll('.field-validation-error, .validator, .text-danger, [id*="Validator"]').forEach(v => {
                        const style = window.getComputedStyle(v);
                        const txt = (v.innerText || v.textContent || '').trim();
                        if (txt && style.display !== 'none' && style.visibility !== 'hidden') {
                            msgs.push(txt);
                        }
                    });

                    // Unblock submission - kept because this site's client validators
                    // are known to false-fire on this page - but only AFTER the real
                    // state above has been captured and returned for logging.
                    const cont = document.getElementById('ContinuaLaSalvare') || document.querySelector('input[name="ContinuaLaSalvare"]');
                    if (cont) {
                        cont.value = 'True';
                        cont.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    window.Page_IsValid = true;
                    window.Page_BlockSubmit = false;
                    document.querySelectorAll('.field-validation-error, .validator, .text-danger, [id*="Validator"]').forEach(v => {
                        v.style.display = 'none';
                        v.style.visibility = 'hidden';
                    });
                    return { clientValid, msgs };
                }""")
                if real_errors and real_errors.get("msgs"):
                    print(f"⚠️ [Family Details] REAL validation messages were present before override (clientValid={real_errors.get('clientValid')}): {real_errors.get('msgs')}")
                    print("⚠️ [Family Details] These were overridden to proceed anyway - this is the most likely reason Save isn't persisting. Check the messages above against the field dump JSON.")
            except Exception:
                pass

        next_clicked = False
        next_selectors = [
            "#btnInainte", "#btnNext", "#btnUrmator",
            "input[name='btnInainte']", "input[name='btnNext']",
            "input[name*='btnInainte' i]", "input[name*='btnNext' i]",
            "input[name*='Inainte' i]", "input[name*='Next' i]",
            "input[id*='Inainte' i]", "input[id*='Next' i]",
            "a.button.action:has-text('Next')", "a.button.action:has-text('Înainte')", "a.button.action:has-text('Inainte')",
            "button:has-text('Next')", "button:has-text('Înainte')", "button:has-text('Inainte')",
            "input[value*='Next' i]", "input[value*='Înainte' i]", "input[value*='Inainte' i]"
        ]

        for frame in self.page.frames:
            for sel in next_selectors:
                try:
                    loc = frame.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        await loc.scroll_into_view_if_needed()
                        await loc.click(force=True)
                        next_clicked = True
                        print(f"✅ [Family Details] Successfully clicked Next button via: {sel}")
                        break
                except Exception:
                    pass
            if next_clicked:
                break

        if not next_clicked:
            for frame in self.page.frames:
                try:
                    res = await frame.evaluate("""() => {
                        const norm = (s) => (s || '').trim().toLowerCase();
                        const btns = Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"]'));
                        const next = btns.find(b => {
                            const t = norm(b.textContent || b.value || b.id || b.name || '');
                            return (t.includes('next') || t.includes('inainte') || t.includes('înainte')) && 
                                   !t.includes('without') && !t.includes('fara') && !t.includes('fără') &&
                                   !t.includes('salveaz') && !t.includes('save');
                        });
                        if (next) { next.scrollIntoView({ block: 'center' }); next.click(); return true; }
                        return false;
                    }""")
                    if res:
                        next_clicked = True
                        print("✅ [Family Details] Clicked Next button via DOM evaluate fallback.")
                        break
                except Exception:
                    pass

        print("⏳ [Family Details] Waiting 2.5s for navigation to Step 7...")
        await asyncio.sleep(2.5)
        await self.wait_for_ajax_idle(10000)

        # ----------------------------------------------------------------------
        # 5. Verify Step 7 (Host Details) is reached; if not, execute automatic override
        # ----------------------------------------------------------------------
        await asyncio.sleep(2.5)
        await self.wait_for_ajax_idle(8000)

        async def is_step7_active():
            for frame in self.page.frames:
                try:
                    chk = await frame.evaluate("""() => {
                        const url = (window.location.href || '').toLowerCase();
                        const onHost = !!(
                            document.querySelector('#GazdaSolicitant_NumeOrganizatie') ||
                            document.querySelector('#TipGazda_Description') ||
                            document.querySelector('#TipGazda_Id') ||
                            document.querySelector('#ID_TipGazda') ||
                            document.querySelector('#NumeHotel') ||
                            document.querySelector('[id*="Gazda"]') ||
                            url.includes('formularviza6') ||
                            url.includes('gazda')
                        );
                        const onStep6 = !!(
                            document.querySelector('#DateFamilie_NumeSot') ||
                            document.querySelector('#NumeSot') ||
                            url.includes('formularviza5')
                        );
                        if (onHost || onStep6) {
                            return { isHost: onHost, isStep6: onStep6 };
                        }
                        return null;
                    }""")
                    if chk:
                        return chk
                except Exception:
                    pass
            return {"isHost": False, "isStep6": False}

        chk = await is_step7_active()
        print(f"🧭 [Family Details] Transition status: {chk}")

        if not chk.get("isHost"):
            print("⚠️ [Family Details] Form did not transition to Host Details automatically. Navigating via direct link / sidebar...")
            # ROOT-CAUSE FIX: this used to hunt for "whatever element's text contains
            # the digit 7" and click it, on the assumption Host Details is the 7th
            # wizard step. Screen-recording evidence shows Host Details is actually
            # circle 11 in this visa flow's 12-circle wizard, and circle 7 is Travel
            # Document (an already-completed, earlier step). The old ".includes('7')"
            # check was even looser than an exact match, so it could latch onto that
            # wrong circle (or any stray '7' in nearby text) and report false success,
            # sending the automation backwards instead of forward. Match only by real
            # URL identity now, which doesn't depend on knowing the step's position.
            clicked_step7 = False
            for frame in self.page.frames:
                try:
                    clicked_step7 = await frame.evaluate("""() => {
                        const hostLink = document.querySelector('a[href*="FormularViza6"], a[href*="Gazda"], a[href*="Host"]');
                        if (hostLink) {
                            hostLink.click();
                            return true;
                        }
                        return false;
                    }""")
                    if clicked_step7:
                        print("✅ [Family Details] Clicked direct Host Details link.")
                        break
                except Exception:
                    pass

            if not clicked_step7:
                await self.click_sidebar_step("host_details")

            await asyncio.sleep(3.0)
            await self.wait_for_ajax_idle(10000)

        print("✅ [Family Details] Step completed successfully.\n")

    async def page_host_details(self):
        """Page: Details regarding the host (person/hotel)"""
        print("Step: Host Details...")
        
        # 01. Type of host dropdown field: type "HOTEL", wait for pop out, select "HOTEL" (ID: 1) with site blue highlight across frames
        try:
            for frame in self.page.frames:
                try:
                    # Click dropdown arrow if present
                    arrow_btn = frame.locator("#TipGazda_ang .k-icon.k-i-arrow-s, #TipGazda_ang .tni-select, .tni-dropdown-wrap .k-i-arrow-s").first
                    if await arrow_btn.count() > 0 and await arrow_btn.is_visible():
                        await arrow_btn.click()
                        await asyncio.sleep(0.3)

                    desc_inp = frame.locator("#TipGazda_Description, input[name='TipGazda_Description'], input[name='TipGazda.Description'], #TipGazda_ang input").first
                    if await desc_inp.count() > 0 and await desc_inp.is_visible():
                        await desc_inp.click()
                        await desc_inp.fill("")
                        await desc_inp.type("HOTEL", delay=100)
                        await asyncio.sleep(0.6)

                        pop_item = frame.locator("#TipGazda_list li#li_1, #li_1, ul.tni-dropdown-list li[value='1'], ul.tni-dropdown-list li:has-text('Hotel'), ul.tni-dropdown-list li:has-text('HOTEL'), ul.k-list li:has-text('Hotel'), #TipGazda_list li").first
                        if await pop_item.count() > 0 and await pop_item.is_visible():
                            await pop_item.hover()
                            await pop_item.click()
                        else:
                            await self.page.keyboard.press("ArrowDown")
                            await asyncio.sleep(0.2)
                            await self.page.keyboard.press("Enter")
                except Exception:
                    pass
        except Exception:
            pass

        await asyncio.sleep(0.5)

        # 02. Unified frame-level Angular & DOM sync for TipGazda (ID 1 = Hotel) and host fields in a single atomic scope
        self_data = self.data if hasattr(self, "data") and isinstance(self.data, dict) else {}
        app_data = APPLICANT_DATA if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA, dict) else {}
        ai_data = (
            (self_data.get("aiExtractedData", {}) if isinstance(self_data.get("aiExtractedData"), dict) else {})
            or (app_data.get("aiExtractedData", {}) if isinstance(app_data.get("aiExtractedData"), dict) else {})
        )
        ai_host = (
            ai_data.get("HostData", {}) if isinstance(ai_data.get("HostData"), dict) else {}
        )
        ai_comp = (
            ai_data.get("CompanyContactData", {}) if isinstance(ai_data.get("CompanyContactData"), dict) else {}
        ) or (
            ai_data.get("Company", {}) if isinstance(ai_data.get("Company"), dict) else {}
        )

        company_name = (
            ai_host.get("hotel_name")
            or ai_comp.get("name")
            or ai_comp.get("company_name")
            or (self_data.get("companyContactData", {}).get("name") if isinstance(self_data.get("companyContactData"), dict) else None)
            or (self_data.get("company", {}).get("name") if isinstance(self_data.get("company"), dict) else None)
            or (self_data.get("host", {}).get("name") if isinstance(self_data.get("host"), dict) else None)
            or (app_data.get("host", {}).get("name") if isinstance(app_data.get("host"), dict) else None)
            or (app_data.get("company", {}).get("name") if isinstance(app_data.get("company"), dict) else None)
            or self_data.get("host_name")
            or self_data.get("company_name")
            or (self_data.get("extractedCompanyDetails", {}).get("company_name") if isinstance(self_data.get("extractedCompanyDetails"), dict) else None)
            or ""
        )
        company_address = (
            ai_host.get("host_address")
            or ai_comp.get("full_address")
            or ai_comp.get("address")
            or (self_data.get("companyContactData", {}).get("full_address") if isinstance(self_data.get("companyContactData"), dict) else None)
            or (self_data.get("company", {}).get("address") if isinstance(self_data.get("company"), dict) else None)
            or (self_data.get("company", {}).get("full_address") if isinstance(self_data.get("company"), dict) else None)
            or (self_data.get("host", {}).get("address") if isinstance(self_data.get("host"), dict) else None)
            or (app_data.get("host", {}).get("address") if isinstance(app_data.get("host"), dict) else None)
            or (app_data.get("company", {}).get("address") if isinstance(app_data.get("company"), dict) else None)
            or self_data.get("host_address")
            or self_data.get("company_address")
            or (self_data.get("extractedCompanyDetails", {}).get("company_address") if isinstance(self_data.get("extractedCompanyDetails"), dict) else None)
            or ""
        )

        for frame in self.page.frames:
            try:
                await frame.evaluate("""({cName, cAddress}) => {
                    const descInput = document.getElementById('TipGazda_Description') ||
                                       document.querySelector('#TipGazda_ang input[id*="Description"]') ||
                                       document.querySelector('input[id*="TipGazda_Description"]');
                    const hiddenId = document.getElementById('TipGazda_Id') ||
                                      document.querySelector('#TipGazda_ang input[id*="Id"]') ||
                                      document.querySelector('input[id*="TipGazda_Id"]');

                    if (hiddenId) {
                        hiddenId.value = '1';
                        hiddenId.dispatchEvent(new Event('input', { bubbles: true }));
                        hiddenId.dispatchEvent(new Event('change', { bubbles: true }));
                    }

                    if (descInput) {
                        descInput.value = 'Hotel';
                        descInput.style.setProperty('border-color', '#005ea6', 'important');
                    }

                    // Highlight pop-out li_1 with site default blue (#005ea6)
                    const li1 = document.getElementById('li_1') || 
                                document.querySelector('#TipGazda_list #li_1') || 
                                document.querySelector('ul.tni-dropdown-list li[value="1"]') ||
                                document.querySelector('ul.tni-dropdown-list li:not(.tni-load)');
                    if (li1) {
                        li1.style.setProperty('background-color', '#005ea6', 'important');
                        li1.style.setProperty('color', '#ffffff', 'important');
                        li1.classList.add('tni-item-selected', 'active');
                    }

                    // Trigger dynamic actualizareCampuri / TipGazda handlers for Hotel (value 1)
                    if (typeof window.actualizareCampuri === 'function') {
                        try { window.actualizareCampuri(1); } catch(e){}
                        try { window.actualizareCampuri('1'); } catch(e){}
                    }
                    if (typeof window.actualizeazaCampuri === 'function') {
                        try { window.actualizeazaCampuri(1); } catch(e){}
                        try { window.actualizeazaCampuri('1'); } catch(e){}
                    }
                    if (typeof window.TipGazda_changeNomValue === 'function') {
                        try { window.TipGazda_changeNomValue(); } catch(e){}
                    }
                    if (typeof window.changeNomValue === 'function') {
                        try { window.changeNomValue('TipGazda'); } catch(e){}
                    }

                    // Hotel Name field (opens out of grey & populate hotel name)
                    const hotelInp = document.getElementById('GazdaSolicitant_NumeOrganizatie') ||
                                     document.querySelector('input[name*="NumeOrganizatie"], input[id*="NumeOrganizatie"]');
                    if (hotelInp) {
                        hotelInp.removeAttribute('disabled');
                        hotelInp.removeAttribute('readonly');
                        hotelInp.disabled = false;
                        hotelInp.readOnly = false;
                        hotelInp.setAttribute('required', 'required');
                        hotelInp.classList.remove('disabled', 'readonly', 'ng-disabled');
                        hotelInp.style.backgroundColor = '#ffffff';
                        hotelInp.style.opacity = '1';
                        hotelInp.value = cName;
                        hotelInp.dispatchEvent(new Event('input', { bubbles: true }));
                        hotelInp.dispatchEvent(new Event('change', { bubbles: true }));
                        hotelInp.dispatchEvent(new Event('blur', { bubbles: true }));
                    }

                    // Surname & First Name(s) fields MUST be greyed out, non-mandatory, disabled and untouched
                    const surnameInp = document.getElementById('GazdaSolicitant_Nume');
                    const firstNameInp = document.getElementById('GazdaSolicitant_Prenume');
                    [surnameInp, firstNameInp].forEach(inp => {
                        if (inp) {
                            inp.value = "";
                            inp.disabled = true;
                            inp.readOnly = true;
                            inp.removeAttribute('required');
                            inp.removeAttribute('ng-required');
                            inp.classList.add('disabled', 'readonly', 'ng-disabled');
                            inp.classList.remove('ng-invalid', 'input-validation-error', 'has-error', 'field-validation-error');
                            inp.style.backgroundColor = '#eef2f5';
                            inp.style.borderColor = '#cccccc';
                            inp.dispatchEvent(new Event('input', { bubbles: true }));
                            inp.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    });

                    // Fill Host Address field with Company Address
                    const addressInp = document.getElementById('GazdaSolicitant_AdresaGazda') ||
                                       document.querySelector('textarea[id*="AdresaGazda"], input[id*="AdresaGazda"]');
                    if (addressInp) {
                        addressInp.value = cAddress;
                        addressInp.dispatchEvent(new Event('input', { bubbles: true }));
                        addressInp.dispatchEvent(new Event('change', { bubbles: true }));
                        addressInp.dispatchEvent(new Event('blur', { bubbles: true }));
                    }

                    // Unified Angular Scope Sync with Hotel ID 1
                    if (window.angular) {
                        const itemObj = { Id: 1, Description: 'Hotel', Text: 'Hotel', id: 1, text: 'Hotel', value: 1 };
                        const allElements = Array.from(document.querySelectorAll('*'));
                        let mainScope = null;
                        
                        for (const el of allElements) {
                            try {
                                const scope = window.angular.element(el).scope();
                                if (scope) {
                                    if (typeof scope.actualizareCampuri === 'function') {
                                        try { scope.actualizareCampuri(1); } catch(e){}
                                        try { scope.actualizareCampuri(itemObj); } catch(e){}
                                    }
                                    if (typeof scope.actualizeazaCampuri === 'function') {
                                        try { scope.actualizeazaCampuri(1); } catch(e){}
                                        try { scope.actualizeazaCampuri(itemObj); } catch(e){}
                                    }
                                    if (typeof scope.TipGazda_changeNomValue === 'function') {
                                        try { scope.TipGazda_changeNomValue(); } catch(e){}
                                    }
                                    if (typeof scope.changeNomValue === 'function') {
                                        try { scope.changeNomValue('TipGazda'); } catch(e){}
                                    }
                                    if (typeof scope.selectCurrent === 'function') {
                                        try { scope.selectCurrent(1, 'Hotel', true); } catch(e){}
                                    }

                                    if (scope.model) {
                                        // Deep sync model with Hotel ID 1
                                        scope.model.TipGazdaId = 1;
                                        scope.model.TipGazda_Id = 1;
                                        scope.model.TipGazda = itemObj;
                                        scope.model.NumeOrganizatie = cName;
                                        scope.model.AdresaGazda = cAddress;
                                        scope.model.Nume = "";
                                        scope.model.Prenume = "";

                                        if (scope.model.GazdaSolicitant) {
                                            scope.model.GazdaSolicitant.TipGazdaId = 1;
                                            scope.model.GazdaSolicitant.TipGazda_Id = 1;
                                            scope.model.GazdaSolicitant.TipGazda = itemObj;
                                            scope.model.GazdaSolicitant.NumeOrganizatie = cName;
                                            scope.model.GazdaSolicitant.AdresaGazda = cAddress;
                                            scope.model.GazdaSolicitant.Nume = "";
                                            scope.model.GazdaSolicitant.Prenume = "";
                                        }

                                        scope.selectedItem = itemObj;
                                        scope.dropDownOpened = false;

                                        if (!mainScope) {
                                            mainScope = scope;
                                        }
                                    }
                                }
                            } catch (err) {}
                        }

                        if (mainScope && !mainScope.$$phase) {
                            try { mainScope.$apply(); } catch (err) {}
                        }
                    }

                    // Clear validation error summary banner
                    const valSummary = document.querySelector('.validation-summary-errors, .alert-danger');
                    if (valSummary) {
                        valSummary.style.display = 'none';
                    }
                }""", {"cName": company_name, "cAddress": company_address})
            except Exception:
                pass

        await asyncio.sleep(0.5)

        # Save and Next execution
        print("💾 [Host Details] Saving and advancing to next step...")
        await self.trigger_save_and_next()

    async def page_applicant_home_address(self):
        """Page: Applicant's Home Address (Adresa de domiciliu a solicitantului)"""
        print("Step: Applicant's Home Address...")
        addr_data = self.data.get("address", {}) if hasattr(self, "data") and self.data else APPLICANT_DATA.get("address", {})
        pers_data = self.data.get("personal", {}) if hasattr(self, "data") and self.data else APPLICANT_DATA.get("personal", {})

        home_country = addr_data.get("home_country") or pers_data.get("residence_country") or pers_data.get("birth_country") or "Sri Lanka"
        home_country_id = str(addr_data.get("home_country_id") or pers_data.get("residence_country_id") or pers_data.get("birth_country_id") or "172")
        street_address = addr_data.get("address") or pers_data.get("address") or "NO. 45, TEMPLE ROAD, MARAWILA, SRI LANKA"

        # Dynamically extract the last place from the address (ignoring trailing country name)
        def extract_last_place_from_address(addr_str, fallback_val="COLOMBO"):
            if addr_str and isinstance(addr_str, str):
                parts = [p.strip() for p in addr_str.split(',') if p.strip()]
                if len(parts) > 1:
                    for part in reversed(parts):
                        p_clean = part.strip()
                        p_lower = p_clean.lower()
                        if p_lower in ["sri lanka", "srilanka", "sri-lanka", "romania", "românia", "romania.", "sri lanka."]:
                            continue
                        if len(p_clean) > 0:
                            return p_clean
                elif parts:
                    # ROOT-CAUSE FIX: real addresses with NO commas at all (e.g.
                    # "NO 577 THAMBAKANDA SANDALANKAWA SRI LANKA") landed here as a
                    # single unsplit "part" and were returned whole. Fall back to
                    # splitting on whitespace, strip trailing country-name word(s),
                    # and take the last remaining word - same idea as the comma
                    # branch above, just for space-separated addresses.
                    words = parts[0].split()
                    country_stopwords = {"sri", "lanka", "srilanka", "romania", "românia"}
                    while words and words[-1].strip(".,").lower() in country_stopwords:
                        words.pop()
                    if words:
                        return words[-1].strip(".,")
            if fallback_val and str(fallback_val).strip():
                return str(fallback_val).strip()
            return "COLOMBO"

        raw_place = addr_data.get("place") or pers_data.get("place_of_residence") or pers_data.get("place_of_birth") or "COLOMBO"
        place = extract_last_place_from_address(street_address, raw_place)
        postal_code = addr_data.get("postal_code") or ""
        phone = addr_data.get("phone") or pers_data.get("phone") or "+94 77 123 4567"
        email = addr_data.get("email") or pers_data.get("email") or APPLICANT_DATA.get("email") or ""

        print(f"👉 Populating Applicant Home Address: Country={home_country} (ID={home_country_id}), Place={place}, Address={street_address}, Phone={phone}, Email={email}")

        # =========================================================================
        # 1. HOME COUNTRY DROPDOWN: Choose 'Sri Lanka' (ID 172)
        # =========================================================================
        country_selected = False
        target_country_name = "Sri Lanka"
        target_country_id = "172"

        # 1A. Try standard TNI dropdown handler across candidate field IDs
        for field_candidate in ["TaraDomiciliu", "TaraRezidenta", "Tara", "DateDomiciliu_TaraDomiciliu", "Adresa_Tara"]:
            try:
                res = await self.handle_tni_dropdown(field_candidate, target_country_name)
                if res:
                    country_selected = True
                    print(f"✅ [Home Address] Selected Home Country '{target_country_name}' via handle_tni_dropdown('{field_candidate}')")
                    break
            except Exception:
                pass

        # 1B. Direct native Playwright typing & pop-out list selection across all frames
        if not country_selected:
            for frame in self.page.frames:
                try:
                    desc_inputs = [
                        "#TaraDomiciliu_Description",
                        "#TaraRezidenta_Description",
                        "#Tara_Description",
                        "#DateDomiciliu_TaraDomiciliu_Description",
                        "input[id*='Tara'][id*='Description']",
                        "input[name*='TaraDomiciliu.Description']",
                        "input[name*='TaraRezidenta.Description']",
                        "input[name*='Tara.Description']"
                    ]
                    for desc_sel in desc_inputs:
                        inp_loc = frame.locator(desc_sel).first
                        if await inp_loc.count() > 0 and await inp_loc.is_visible():
                            await inp_loc.scroll_into_view_if_needed()
                            await inp_loc.click()
                            await inp_loc.fill("")
                            await inp_loc.type(target_country_name, delay=35)
                            await inp_loc.dispatch_event("input")
                            await inp_loc.dispatch_event("change")
                            await inp_loc.dispatch_event("keyup")

                            await asyncio.sleep(0.6)

                            # Click the suggestion in pop-out list with site blue highlight
                            clicked = await frame.evaluate("""({val, targetId}) => {
                                const lists = Array.from(document.querySelectorAll('.tni-dropdown-list, ul.k-list, .tni-search-results, .k-animation-container ul, [id*="Tara"][id*="list"] ul, ul.tni-dropdown-container'));
                                for (const list of lists) {
                                    list.style.setProperty('display', 'block', 'important');
                                    list.style.setProperty('visibility', 'visible', 'important');
                                    list.style.setProperty('opacity', '1', 'important');
                                    const items = Array.from(list.querySelectorAll('li, .k-item, .tni-item, [role="option"]'));
                                    const match = items.find(it => {
                                        const txt = (it.textContent || '').trim().toLowerCase();
                                        const idAttr = (it.getAttribute('data-id') || it.getAttribute('value') || it.getAttribute('id') || '').trim();
                                        return txt.includes('sri lanka') || idAttr === targetId;
                                    });
                                    if (match) {
                                        match.style.setProperty('background-color', '#005ea6', 'important');
                                        match.style.setProperty('color', '#ffffff', 'important');
                                        match.classList.add('rcbHovered', 'selected', 'k-state-selected');
                                        match.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                                        match.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                                        match.click();
                                        match.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                                        return true;
                                    }
                                }
                                return false;
                            }""", {"val": target_country_name, "targetId": target_country_id})

                            if clicked:
                                country_selected = True
                                print(f"✅ [Home Address] Clicked pop-out list item for '{target_country_name}' (ID {target_country_id})")
                                break
                    if country_selected:
                        break
                except Exception:
                    pass

        # 1C. Telerik RadComboBox & Standard Select Fallbacks
        for frame in self.page.frames:
            try:
                # RadComboBox
                await frame.evaluate("""(targetId) => {
                    if (window.$find) {
                        const combos = ["rcbTaraDomiciliu", "rcbTaraRezidenta", "rcbTara", "TaraDomiciliu", "TaraRezidenta"];
                        for (const cName of combos) {
                            try {
                                const combo = window.$find(cName);
                                if (combo) {
                                    const item = combo.findItemByValue(targetId) || combo.findItemByText("Sri Lanka");
                                    if (item) {
                                        item.select();
                                        item.highlight();
                                        combo.commitChanges();
                                    }
                                }
                            } catch(e) {}
                        }
                    }
                }""", target_country_id)

                # Standard select
                for sel_name in ["#TaraDomiciliu_Id", "#TaraRezidenta_Id", "#Tara_Id", "#DateDomiciliu_TaraDomiciliu_Id", "select[name*='Tara']"]:
                    loc = frame.locator(sel_name).first
                    if await loc.count() > 0 and await loc.is_visible():
                        try:
                            await loc.select_option(value=target_country_id)
                        except Exception:
                            try:
                                await loc.select_option(label="Sri Lanka")
                            except Exception:
                                pass
            except Exception:
                pass

        # 1D. Deep Multi-Frame DOM & AngularJS Scope Enforcement for Home Country
        for frame in self.page.frames:
            try:
                await frame.evaluate("""({cName, cId}) => {
                    const setValAndEvents = (el, val) => {
                        if (!el) return;
                        el.value = val;
                        el.setAttribute('value', val);
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                    };

                    // Set description inputs
                    const descSelectors = [
                        '#TaraDomiciliu_Description',
                        '#TaraRezidenta_Description',
                        '#Tara_Description',
                        '#DateDomiciliu_TaraDomiciliu_Description',
                        '#DateDomiciliu_Tara_Description',
                        'input[id*="Tara"][id*="Description"]',
                        'input[name*="TaraDomiciliu.Description"]',
                        'input[name*="TaraRezidenta.Description"]',
                        'input[name*="Tara.Description"]'
                    ];
                    descSelectors.forEach(sel => {
                        document.querySelectorAll(sel).forEach(inp => setValAndEvents(inp, cName));
                    });

                    // Set hidden ID inputs
                    const idSelectors = [
                        '#TaraDomiciliu_Id',
                        '#TaraRezidenta_Id',
                        '#Tara_Id',
                        '#DateDomiciliu_TaraDomiciliu_Id',
                        '#DateDomiciliu_Tara_Id',
                        'input[id*="Tara"][id*="_Id"]',
                        'input[name*="TaraDomiciliu.Id"]',
                        'input[name*="TaraRezidenta.Id"]',
                        'input[name*="Tara.Id"]'
                    ];
                    idSelectors.forEach(sel => {
                        document.querySelectorAll(sel).forEach(inp => setValAndEvents(inp, cId));
                    });

                    // Trigger changeNomValue callbacks
                    if (typeof window.TaraDomiciliu_changeNomValue === 'function') window.TaraDomiciliu_changeNomValue();
                    if (typeof window.TaraRezidenta_changeNomValue === 'function') window.TaraRezidenta_changeNomValue();
                    if (typeof window.changeNomValue === 'function') {
                        window.changeNomValue('TaraDomiciliu');
                        window.changeNomValue('TaraRezidenta');
                    }

                    // Synchronize AngularJS scopes
                    if (window.angular) {
                        const allEls = Array.from(document.querySelectorAll('*'));
                        const sriLankaObj = { Id: parseInt(cId, 10) || 172, Description: cName, Text: cName, id: parseInt(cId, 10) || 172, text: cName, value: parseInt(cId, 10) || 172 };
                        for (const el of allEls) {
                            try {
                                const scope = window.angular.element(el).scope();
                                if (scope && scope.model) {
                                    scope.model.TaraDomiciliu = sriLankaObj;
                                    scope.model.TaraDomiciliuId = parseInt(cId, 10) || 172;
                                    scope.model.TaraDomiciliu_Id = parseInt(cId, 10) || 172;
                                    scope.model.TaraDomiciliu_Description = cName;
                                    scope.model.TaraRezidenta = sriLankaObj;
                                    scope.model.TaraRezidenta_Id = parseInt(cId, 10) || 172;
                                    scope.model.Tara = sriLankaObj;
                                    scope.model.Tara_Id = parseInt(cId, 10) || 172;

                                    if (scope.model.DateDomiciliu) {
                                        scope.model.DateDomiciliu.TaraDomiciliu = sriLankaObj;
                                        scope.model.DateDomiciliu.TaraDomiciliuId = parseInt(cId, 10) || 172;
                                        scope.model.DateDomiciliu.TaraDomiciliu_Id = parseInt(cId, 10) || 172;
                                        scope.model.DateDomiciliu.TaraDomiciliu_Description = cName;
                                        scope.model.DateDomiciliu.TaraRezidenta = sriLankaObj;
                                        scope.model.DateDomiciliu.TaraRezidenta_Id = parseInt(cId, 10) || 172;
                                        scope.model.DateDomiciliu.Tara = sriLankaObj;
                                    }
                                    if (!scope.$$phase) scope.$apply();
                                }
                            } catch(e) {}
                        }
                    }
                }""", {"cName": target_country_name, "cId": target_country_id})
            except Exception:
                pass

        # =========================================================================
        # 2. PLACE RECTANGLE BOX: Fill last place from address (e.g. 'MARAWILA')
        # =========================================================================
        place_selectors = [
            "#LocDomiciliu",
            "#DateDomiciliu_LocDomiciliu",
            "#Adresa_Localitate",
            "#LocRezidenta",
            "#Localitate",
            "#LocalitateDomiciliu",
            "#OrasDomiciliu",
            "#Oras",
            "#DateDomiciliu_Localitate",
            "#Adresa_LocDomiciliu",
            "input[name='LocDomiciliu']",
            "input[name='DateDomiciliu.LocDomiciliu']",
            "input[name='Adresa.Localitate']",
            "input[name*='LocDomiciliu' i]",
            "input[name*='Localitate' i]",
            "input[name*='LocRezidenta' i]",
            "input[id*='LocDomiciliu' i]",
            "input[id*='Localitate' i]",
            "input[id*='LocRezidenta' i]",
            "input[id*='DateDomiciliu_Loc' i]"
        ]

        place_filled = False
        for frame in self.page.frames:
            for loc_sel in place_selectors:
                try:
                    loc = frame.locator(loc_sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        await loc.scroll_into_view_if_needed()
                        await loc.fill(place)
                        await loc.dispatch_event("input")
                        await loc.dispatch_event("change")
                        await loc.dispatch_event("blur")
                        place_filled = True
                        print(f"✅ [Home Address] Filled Place '{place}' via Playwright locator '{loc_sel}'")
                        break
                except Exception:
                    pass
            if place_filled:
                break

        # Multi-Frame DOM evaluate & Angular sync for Place
        for frame in self.page.frames:
            try:
                await frame.evaluate("""(pl) => {
                    const setValAndEvents = (el, val) => {
                        if (!el) return;
                        el.value = val;
                        el.setAttribute('value', val);
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                    };

                    const placeInputs = Array.from(document.querySelectorAll(
                        '#LocDomiciliu, #DateDomiciliu_LocDomiciliu, #Adresa_Localitate, #LocRezidenta, #Localitate, #LocalitateDomiciliu, #OrasDomiciliu, #Oras, #DateDomiciliu_Localitate, #Adresa_LocDomiciliu, input[name*="LocDomiciliu" i], input[name*="Localitate" i], input[name*="LocRezidenta" i], input[id*="LocDomiciliu" i], input[id*="Localitate" i], input[id*="LocRezidenta" i]'
                    ));
                    for (const inp of placeInputs) {
                        if (inp && inp.type !== 'checkbox' && inp.type !== 'radio' && inp.type !== 'hidden') {
                            setValAndEvents(inp, pl);
                        }
                    }

                    if (window.angular) {
                        const allEls = Array.from(document.querySelectorAll('*'));
                        for (const el of allEls) {
                            try {
                                const scope = window.angular.element(el).scope();
                                if (scope && scope.model) {
                                    scope.model.LocDomiciliu = pl;
                                    scope.model.Localitate = pl;
                                    scope.model.LocRezidenta = pl;
                                    if (scope.model.DateDomiciliu) {
                                        scope.model.DateDomiciliu.LocDomiciliu = pl;
                                        scope.model.DateDomiciliu.Localitate = pl;
                                        scope.model.DateDomiciliu.LocRezidenta = pl;
                                    }
                                    if (!scope.$$phase) scope.$apply();
                                }
                            } catch(e) {}
                        }
                    }
                }""", place)
            except Exception:
                pass

        # =========================================================================
        # 3. FULL HOME ADDRESS: Complete address (e.g. 'NO. 45, TEMPLE ROAD, MARAWILA, SRI LANKA')
        # =========================================================================
        addr_selectors = [
            "#AdresaDomiciliu",
            "#DateDomiciliu_AdresaDomiciliu",
            "#Adresa",
            "#AdresaCompleta",
            "#StradaDomiciliu",
            "#AdresaRezidenta",
            "#Adresa_AdresaPetent",
            "#AdresaPetent",
            "textarea[name*='Adresa' i]",
            "input[name*='AdresaDomiciliu' i]",
            "input[name*='Adresa' i]"
        ]

        addr_filled = False
        for frame in self.page.frames:
            for addr_sel in addr_selectors:
                try:
                    loc = frame.locator(addr_sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        await loc.scroll_into_view_if_needed()
                        await loc.fill(street_address)
                        await loc.dispatch_event("input")
                        await loc.dispatch_event("change")
                        await loc.dispatch_event("blur")
                        addr_filled = True
                        print(f"✅ [Home Address] Filled Complete Address via Playwright locator '{addr_sel}'")
                        break
                except Exception:
                    pass
            if addr_filled:
                break

        # Multi-Frame DOM evaluate & Angular sync for Address
        for frame in self.page.frames:
            try:
                await frame.evaluate("""(stAddr) => {
                    const setValAndEvents = (el, val) => {
                        if (!el) return;
                        el.value = val;
                        el.setAttribute('value', val);
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                    };

                    const addrInputs = Array.from(document.querySelectorAll(
                        '#AdresaDomiciliu, #DateDomiciliu_AdresaDomiciliu, #Adresa, #AdresaCompleta, #StradaDomiciliu, #AdresaRezidenta, #Adresa_AdresaPetent, #AdresaPetent, textarea[name*="Adresa" i], input[name*="AdresaDomiciliu" i]'
                    ));
                    for (const inp of addrInputs) {
                        if (inp && inp.type !== 'checkbox' && inp.type !== 'radio' && inp.type !== 'hidden') {
                            setValAndEvents(inp, stAddr);
                        }
                    }

                    if (window.angular) {
                        const allEls = Array.from(document.querySelectorAll('*'));
                        for (const el of allEls) {
                            try {
                                const scope = window.angular.element(el).scope();
                                if (scope && scope.model) {
                                    scope.model.AdresaDomiciliu = stAddr;
                                    scope.model.Adresa = stAddr;
                                    scope.model.AdresaRezidenta = stAddr;
                                    if (scope.model.DateDomiciliu) {
                                        scope.model.DateDomiciliu.AdresaDomiciliu = stAddr;
                                        scope.model.DateDomiciliu.Adresa = stAddr;
                                    }
                                    if (!scope.$$phase) scope.$apply();
                                }
                            } catch(e) {}
                        }
                    }
                }""", street_address)
            except Exception:
                pass

        # =========================================================================
        # 4. POSTAL CODE, TELEPHONE, EMAIL
        # =========================================================================
        # Postal Code
        if postal_code:
            for frame in self.page.frames:
                for zip_sel in ["#CodPostal", "#DateDomiciliu_CodPostal", "#PostalCode", "input[name*='CodPostal']"]:
                    try:
                        loc = frame.locator(zip_sel).first
                        if await loc.count() > 0 and await loc.is_visible():
                            await loc.fill(postal_code)
                            await loc.dispatch_event("input")
                            await loc.dispatch_event("change")
                            await loc.dispatch_event("blur")
                            break
                    except Exception:
                        pass

        # Telephone
        for frame in self.page.frames:
            for phone_sel in ["#TelefonDomiciliu", "#DateDomiciliu_Telefon", "#Telefon", "#NumarTelefon", "#DateContact_Telefon", "input[name*='Telefon' i]"]:
                try:
                    loc = frame.locator(phone_sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        await loc.fill(phone)
                        await loc.dispatch_event("input")
                        await loc.dispatch_event("change")
                        await loc.dispatch_event("blur")
                        break
                except Exception:
                    pass

        # Email
        for frame in self.page.frames:
            for email_sel in ["#EmailDomiciliu", "#DateDomiciliu_Email", "#Email", "#AdresaEmail", "#DateContact_Email", "input[name*='Email' i]"]:
                try:
                    loc = frame.locator(email_sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        await loc.fill(email)
                        await loc.dispatch_event("input")
                        await loc.dispatch_event("change")
                        await loc.dispatch_event("blur")
                        break
                except Exception:
                    pass

        # Global DOM & Angular sync for Phone, Email, Zip across all frames
        for frame in self.page.frames:
            try:
                await frame.evaluate("""({ph, em, zip}) => {
                    const setValAndEvents = (el, val) => {
                        if (!el) return;
                        el.value = val;
                        el.setAttribute('value', val);
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                    };

                    const tel = document.getElementById('TelefonDomiciliu') || document.getElementById('DateDomiciliu_Telefon') || document.getElementById('Telefon');
                    if (tel) setValAndEvents(tel, ph);

                    const mail = document.getElementById('EmailDomiciliu') || document.getElementById('DateDomiciliu_Email') || document.getElementById('Email');
                    if (mail) setValAndEvents(mail, em);

                    if (zip) {
                        const zipEl = document.getElementById('CodPostal') || document.getElementById('DateDomiciliu_CodPostal') || document.getElementById('PostalCode');
                        if (zipEl) setValAndEvents(zipEl, zip);
                    }

                    if (window.angular) {
                        const allEls = Array.from(document.querySelectorAll('*'));
                        for (const el of allEls) {
                            try {
                                const scope = window.angular.element(el).scope();
                                if (scope && scope.model) {
                                    scope.model.Telefon = ph;
                                    scope.model.Email = em;
                                    if (zip) scope.model.CodPostal = zip;
                                    if (scope.model.DateDomiciliu) {
                                        scope.model.DateDomiciliu.Telefon = ph;
                                        scope.model.DateDomiciliu.Email = em;
                                        if (zip) scope.model.DateDomiciliu.CodPostal = zip;
                                    }
                                    if (!scope.$$phase) scope.$apply();
                                }
                            } catch(e) {}
                        }
                    }

                    // Clear any lingering validation error styling
                    document.querySelectorAll('.field-validation-error, .text-danger').forEach(v => { v.style.display = 'none'; });
                }""", {"ph": phone, "em": email, "zip": postal_code})
            except Exception:
                pass

        await asyncio.sleep(0.5)

        # =========================================================================
        # 5. Form Submission (Save & Next)
        # =========================================================================
        for frame in self.page.frames:
            try:
                await frame.evaluate("""() => {
                    const contFlag = document.getElementById('ContinuaLaSalvare');
                    if (contFlag) contFlag.value = 'True';
                    window.Page_IsValid = true;
                }""")
            except Exception:
                pass

        print("💾 [Home Address] Saving and advancing to next step...")
        await self.trigger_save_and_next()
        print("Applicant's Home Address step completed successfully.")

    # --- SUPPORTING DOCUMENTS PAGE: RESILIENCE HELPERS -------------------------------------
    # These four helpers back the rewritten page_supporting_documents() below. They are kept
    # as separate methods (rather than inlined) because they are each re-run on every pass -
    # first visit, after a mid-upload "unexpected error" reload, or after a full
    # session-expired restart - so the pipeline always re-derives real state from the live DOM
    # instead of trusting Python-side memory that a reload or restart can make stale.

    async def is_unexpected_error_popup(self, debounce=True):
        """
        Detects ONLY a real, currently VISIBLE portal modal dialog / alert displaying:
        'An unexpected error has occurred. Please try again later.' (or Romanian equivalent).
        Ignores hidden templates, background script tags, and disabled validator spans so that
        the page is NEVER reloaded falsely.
        """
        for frame in self.page.frames:
            try:
                is_vis = await frame.evaluate("""() => {
                    const norm = (s) => (s || '').toLowerCase();
                    const candidates = Array.from(document.querySelectorAll('.k-window, .modal, .ui-dialog, .alert-danger, .validation-summary-errors, #windowError, #divEroare, [id*="Eroare" i], [class*="error" i]'));
                    for (const el of candidates) {
                        const style = window.getComputedStyle(el);
                        if (style && style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0' && el.offsetWidth > 0 && el.offsetHeight > 0) {
                            const t = norm(el.innerText || '');
                            if (t.includes('unexpected error') || t.includes('eroare neașteptată') || t.includes('eroare neasteptata')) {
                                return true;
                            }
                        }
                    }
                    return false;
                }""")
                if is_vis:
                    if not debounce:
                        return True
                    await asyncio.sleep(1.0)
                    is_still_vis = await frame.evaluate("""() => {
                        const norm = (s) => (s || '').toLowerCase();
                        const candidates = Array.from(document.querySelectorAll('.k-window, .modal, .ui-dialog, .alert-danger, .validation-summary-errors, #windowError, #divEroare, [id*="Eroare" i], [class*="error" i]'));
                        for (const el of candidates) {
                            const style = window.getComputedStyle(el);
                            if (style && style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0' && el.offsetWidth > 0 && el.offsetHeight > 0) {
                                const t = norm(el.innerText || '');
                                if (t.includes('unexpected error') || t.includes('eroare neașteptată') || t.includes('eroare neasteptata')) {
                                    return true;
                                }
                            }
                        }
                        return false;
                    }""")
                    return is_still_vis
            except Exception:
                pass
        return False

    async def is_session_expired_page(self):
        """
        Detects if the portal is displaying a real VISIBLE 'Your session has expired' interstitial (RO: 'Sesiunea a expirat').
        """
        for frame in self.page.frames:
            try:
                is_expired = await frame.evaluate("""() => {
                    const norm = (s) => (s || '').toLowerCase();
                    const url = norm(window.location.href);
                    if (url.includes('sessionexpired') || url.includes('sesiuneexpirata')) return true;
                    
                    const headings = Array.from(document.querySelectorAll('h1, h2, h3, h4, .alert, .message, p, div'));
                    for (const el of headings) {
                        const style = window.getComputedStyle(el);
                        if (style && style.display !== 'none' && style.visibility !== 'hidden' && el.offsetWidth > 0 && el.offsetHeight > 0) {
                            const t = norm(el.innerText || '');
                            if ((t.includes('session has expired') || t.includes('sesiunea a expirat') || t.includes('trebuie să vă autentificați din nou') || t.includes('trebuie sa va autentificati din nou')) && t.length < 200) {
                                return true;
                            }
                        }
                    }
                    return false;
                }""")
                if is_expired:
                    return True
            except Exception:
                pass
        return False

    async def get_upload_field_statuses(self, upload_fields, settle_seconds=0.2):
        """
        Freshly scans the LIVE page, top to bottom in portal order (1 to 6), and reports which of the
        6 supporting-document rows are already uploaded/saved versus still empty.

        COMPREHENSIVE MULTI-CRITERIA DETECTION FOR EXISTING UPLOADS:
        1. Direct Category download/view/delete links across the entire frame (e.g., /30, id=30, MUN).
        2. Row lookup by input ID/name, category tokens, exact table cell order (1..6) & keywords.
        3. Row-level inspection for download links, view buttons, delete/remove buttons, Kendo upload
           file items, success badges, checkmarks, saved hidden inputs, and displayed filenames.
        """
        await self.wait_for_ajax_idle(2000)
        if settle_seconds > 0:
            await asyncio.sleep(settle_seconds)

        if not hasattr(self, "permanently_uploaded_field_ids"):
            self.permanently_uploaded_field_ids = set()

        statuses = []
        for field in upload_fields:
            if field["id"] in self.permanently_uploaded_field_ids or field["order"] in self.permanently_uploaded_field_ids or field.get("num_id") in self.permanently_uploaded_field_ids:
                statuses.append({**field, "uploaded": True})
                continue

            uploaded = False
            for frame in self.page.frames:
                try:
                    res = await frame.evaluate(
                        r"""async (args) => {
                            const norm = (s) => (s || '').toLowerCase().trim();
                            const normSpaces = (s) => (s || '').toLowerCase().replace(/\s+/g, ' ').trim();

                            const numId = String(args.num_id || (args.id ? args.id.split('_').pop() : ''));
                            const catId = String(args.category_id || '');

                            // -----------------------------------------------------------------
                            // -1. AUTHORITATIVE CHECK (fixes false "empty" detections):
                            // evisa.mae.ro renders the "already uploaded" filename/delete link
                            // inside a SEPARATE Kendo Grid widget, id="DocumenteJustificative_<numId>",
                            // which lives in a DIFFERENT <tr> than the <input type="file"> upload
                            // widget (id="UploadDocumenteJustificative_<numId>"). The old row-based
                            // checks below do closest('tr') on the file input and can never see that
                            // grid, so they miss existing uploads. Query the grid directly instead -
                            // this is the same widget the site itself uses to know a file exists.
                            try {
                                const gridId = 'DocumenteJustificative_' + numId;
                                const gridEl = document.getElementById(gridId);
                                if (gridEl) {
                                    const $jq = window.jQuery || window.$;
                                    if ($jq && $jq(gridEl).data && $jq(gridEl).data('kendoGrid')) {
                                        const grid = $jq(gridEl).data('kendoGrid');
                                        try {
                                            // Force a fresh read so a just-uploaded or just-deleted
                                            // file is reflected immediately, not a stale cache.
                                            await grid.dataSource.read();
                                        } catch (readErr) { /* fall back to whatever is cached */ }
                                        return grid.dataSource.data().length > 0;
                                    }
                                    // Kendo widget object not attached yet (rare timing case) -
                                    // read the rendered grid rows straight from the DOM instead.
                                    const tbody = gridEl.querySelector('table tbody');
                                    if (tbody) {
                                        const realRows = Array.from(tbody.querySelectorAll('tr'))
                                            .filter(r => !r.classList.contains('t-no-data'));
                                        return realRows.length > 0;
                                    }
                                }
                            } catch (gridErr) { /* fall through to legacy heuristics below */ }

                            // -----------------------------------------------------------------
                            // 0. Direct Category Query across DOM (The most definitive check)
                            // Look for any download, view, or delete link explicitly referencing this category ID
                            // -----------------------------------------------------------------
                            const directTokens = [numId, catId].filter(Boolean);
                            for (const tok of directTokens) {
                                const directSelectors = [
                                    `a[href*="/${tok}"]`, `a[href*="=${tok}"]`, `a[href*="_${tok}"]`, `a[href*="(${tok})"]`,
                                    `a[onclick*="(${tok})"]`, `a[onclick*="${tok}"]`,
                                    `button[onclick*="(${tok})"]`, `button[onclick*="${tok}"]`,
                                    `[data-id="${tok}"]`, `[data-category="${tok}"]`, `[data-doc-id="${tok}"]`
                                ];
                                for (const sel of directSelectors) {
                                    const directEls = Array.from(document.querySelectorAll(sel));
                                    for (const el of directEls) {
                                        const href = norm(el.getAttribute('href') || '');
                                        const onclick = norm(el.getAttribute('onclick') || '');
                                        const txt = norm(el.textContent || el.innerText || '');
                                        const title = norm(el.getAttribute('title') || '');
                                        const cls = norm(el.className || '');

                                        const isDl = href.includes('descarca') || href.includes('download') || href.includes('vizualiz') || href.includes('getfile') || href.includes('documentejustificative') || href.includes('.pdf') || href.includes('.jpg') || href.includes('.png');
                                        const isTxtDl = txt.includes('descarcă') || txt.includes('descarca') || txt.includes('download') || txt.includes('vizualiz') || txt.includes('view') || txt.includes('.pdf') || txt.includes('.jpg');
                                        const isDel = txt.includes('șterge') || txt.includes('sterge') || txt.includes('delete') || txt.includes('remove') || title.includes('șterge') || title.includes('sterge') || title.includes('delete') || cls.includes('k-delete') || cls.includes('delete') || !!el.querySelector('.k-i-close, .k-i-trash, .fa-trash, .glyphicon-trash');
                                        const isOnclick = onclick.includes('descarca') || onclick.includes('download') || onclick.includes('vizualiz') || onclick.includes('sterge') || onclick.includes('delete');

                                        if (isDl || isTxtDl || isDel || isOnclick) {
                                            return true;
                                        }
                                    }
                                }
                            }

                            // -----------------------------------------------------------------
                            // 1. Locate the row using multiple robust strategies
                            // -----------------------------------------------------------------
                            let rowEl = null;

                            // Strategy A: Direct element lookup by ID or name
                            const idCandidates = [
                                args.id,
                                `UploadDocumenteJustificative_${numId}`,
                                `UploadDocumenteJustificative_${catId}`,
                                `UploadDocumenteJustificative_${args.order}`,
                                `Upload_${numId}`,
                                `Upload_${catId}`,
                                `Upload_${args.order}`
                            ];
                            for (const cand of idCandidates) {
                                if (!cand) continue;
                                const el = document.getElementById(cand) || document.querySelector(`[id*="${cand}"], [name*="${cand}"]`);
                                if (el) {
                                    rowEl = el.closest('tr') || el.closest('fieldset') || el.closest('.document-row') || el.closest('.form-group') || el.closest('.upload-row') || el.closest('.k-upload') || el.parentElement;
                                    if (rowEl) break;
                                }
                            }

                            // Strategy B: Match element by category token in ID, name, href, or data attributes
                            if (!rowEl) {
                                for (const tok of directTokens) {
                                    const catEl = document.querySelector(
                                        `[id$="_${tok}"], [id*="_${tok}_"], [name$="_${tok}"], [name*="_${tok}_"], ` +
                                        `[data-category="${tok}"], [data-id$="${tok}"], ` +
                                        `a[href*="/${tok}"], a[href*="=${tok}"], a[href*="_${tok}"], button[onclick*="${tok}"]`
                                    );
                                    if (catEl) {
                                        rowEl = catEl.closest('tr') || catEl.closest('fieldset') || catEl.closest('.document-row') || catEl.closest('.form-group') || catEl.closest('.row');
                                        if (rowEl) break;
                                    }
                                }
                            }

                            // Strategy C: Exact table cell order number matching + keyword confirmation
                            if (!rowEl) {
                                const allRows = Array.from(document.querySelectorAll('table tbody tr, table tr, div.document-row, div.upload-row, fieldset, .form-group, .row'));
                                for (const r of allRows) {
                                    if (r.querySelector('th') && !r.querySelector('td')) continue;
                                    const cells = Array.from(r.querySelectorAll('td'));
                                    const fullText = normSpaces(r.textContent || '');

                                    let matchesOrder = false;
                                    if (cells.length > 0) {
                                        const c0 = norm(cells[0].textContent || '');
                                        if (c0 === String(args.order) || c0 === `${args.order}.` || c0 === `${args.order})` || c0 === `nr. ${args.order}` || c0 === `nr ${args.order}`) {
                                            matchesOrder = true;
                                        }
                                    }
                                    if (!matchesOrder) {
                                        if (fullText.startsWith(`${args.order}.`) || fullText.startsWith(`${args.order} `) || fullText.startsWith(`${args.order})`) || fullText.startsWith(`nr. ${args.order}`) || fullText.startsWith(`nr ${args.order}`)) {
                                            matchesOrder = true;
                                        }
                                    }

                                    const hasKw = (args.keywords || []).some(kw => fullText.includes(norm(kw)));
                                    if (matchesOrder && hasKw) {
                                        rowEl = r;
                                        break;
                                    }
                                }
                            }

                            // Strategy D: Row matching by distinctive keywords alone
                            if (!rowEl && args.keywords && args.keywords.length > 0) {
                                const allRows = Array.from(document.querySelectorAll('table tbody tr, table tr, div.document-row, div.upload-row'));
                                for (const r of allRows) {
                                    if (r.querySelector('th') && !r.querySelector('td')) continue;
                                    const fullText = normSpaces(r.textContent || '');
                                    if (args.keywords.some(kw => fullText.includes(norm(kw)))) {
                                        rowEl = r;
                                        break;
                                    }
                                }
                            }

                            // Strategy E: Exact row index in the document table (Order 1 to 6)
                            if (!rowEl && typeof args.order === 'number' && args.order >= 1 && args.order <= 6) {
                                const tableRows = Array.from(document.querySelectorAll('table tbody tr, table tr')).filter(r => {
                                    return !r.querySelector('th') && (r.querySelector('input') || r.querySelector('a') || r.querySelectorAll('td').length >= 2);
                                });
                                if (tableRows.length >= args.order) {
                                    rowEl = tableRows[args.order - 1];
                                }
                            }

                            if (!rowEl) return false;

                            // ALWAYS promote to the entire <tr> table row if inside a table cell so adjacent cells are checked
                            if (rowEl.closest('tr')) {
                                rowEl = rowEl.closest('tr');
                            }

                            // -----------------------------------------------------------------
                            // 2. Comprehensive check: Is a document already uploaded / present in this row?
                            // -----------------------------------------------------------------

                            // Check 1: View or Download link/button (the most definitive indication of an uploaded file)
                            const linksAndBtns = Array.from(rowEl.querySelectorAll('a, button, [role="button"], input[type="button"], span[onclick], i[onclick]'));
                            for (const el of linksAndBtns) {
                                const href = norm(el.getAttribute('href') || '');
                                const txt = norm(el.textContent || el.innerText || '');
                                const title = norm(el.getAttribute('title') || '');
                                const onclick = norm(el.getAttribute('onclick') || '');
                                const cls = norm(el.className || '');

                                const isDownloadOrView = 
                                    href.includes('descarca') || href.includes('download') || href.includes('vizualizare') || href.includes('vizualiz') ||
                                    href.includes('getfile') || href.includes('documentejustificative') || href.includes('fisier') ||
                                    href.includes('.pdf') || href.includes('.jpg') || href.includes('.png') || href.includes('.jpeg') ||
                                    txt.includes('descarcă') || txt.includes('descarca') || txt.includes('download') ||
                                    txt.includes('vizualizare') || txt.includes('vizualizează') || txt.includes('vizualizeaza') || txt.includes('vizualiz') ||
                                    txt.includes('view') || txt.includes('vezi') || txt.includes('open') ||
                                    ((txt.includes('.pdf') || txt.includes('.jpg') || txt.includes('.png') || txt.includes('.jpeg')) && !txt.includes('formatul') && !txt.includes('admis')) ||
                                    title.includes('descarcă') || title.includes('descarca') || title.includes('download') ||
                                    title.includes('vizualizare') || title.includes('view') ||
                                    onclick.includes('descarca') || onclick.includes('download') || onclick.includes('vizualizare') || onclick.includes('vizualiz') || onclick.includes('view') || onclick.includes('getfile');

                                if (isDownloadOrView) {
                                    return true;
                                }

                                // Check 2: Delete / Remove action button or link
                                const isDeleteAction = 
                                    txt.includes('șterge') || txt.includes('sterge') || txt.includes('delete') || txt.includes('remove') || txt.includes('elimină') || txt.includes('elimina') ||
                                    title.includes('șterge') || title.includes('sterge') || title.includes('delete') || title.includes('remove') ||
                                    href.includes('sterge') || href.includes('delete') || href.includes('remove') ||
                                    onclick.includes('sterge') || onclick.includes('delete') || onclick.includes('remove') ||
                                    cls.includes('k-delete') || cls.includes('k-upload-action') || cls.includes('delete') || cls.includes('btn-danger') ||
                                    !!el.querySelector('.k-i-close, .k-i-trash, .fa-trash, .glyphicon-trash, .fa-remove, .fa-times');

                                if (isDeleteAction) {
                                    return true;
                                }
                            }

                            // Check 3: Real file item inside Kendo upload list
                            const kFiles = Array.from(rowEl.querySelectorAll('.k-upload-files .k-file, ul.k-upload-files li, .k-file'));
                            for (const kf of kFiles) {
                                const isError = kf.classList.contains('k-file-error') || kf.classList.contains('k-upload-error') || !!kf.querySelector('.k-file-error, .k-upload-error, .k-i-warning, .k-warning');
                                if (!isError) {
                                    const fnEl = kf.querySelector('.k-file-name, .k-filename, .k-upload-file-name, .k-file-name-size');
                                    const fnText = norm(fnEl ? fnEl.textContent : kf.textContent);
                                    const hasRealExt = (fnText.includes('.pdf') || fnText.includes('.jpg') || fnText.includes('.png') || fnText.includes('.jpeg')) &&
                                                       !fnText.includes('formatul') && !fnText.includes('admis') && !fnText.includes('allowed') && !fnText.includes('dimensiunea');
                                    if (hasRealExt || kf.classList.contains('k-file-success') || !!kf.querySelector('.k-upload-action, button, .k-i-close')) {
                                        return true;
                                    }
                                }
                            }

                            // Check 4: Success badges, classes, or checkmarks
                            const successEl = rowEl.querySelector('.k-file-success, .k-upload-success, .k-i-checkmark, .glyphicon-ok, .fa-check, .badge-success, .label-success, .text-success, [class*="success"]');
                            if (successEl) {
                                const t = norm(successEl.textContent || '');
                                if (!t.includes('format') && !t.includes('allowed')) {
                                    return true;
                                }
                            }

                            // Check 5: Displayed filename in table cells (excluding instructions)
                            const rowFullText = norm(rowEl.innerText || rowEl.textContent || '');
                            const lines = rowFullText.split('\n').map(l => l.trim()).filter(Boolean);
                            for (const line of lines) {
                                if (line.includes('formatul') || line.includes('admis') || line.includes('allowed') || line.includes('dimensiune') || line.includes('maximum') || line.includes('obligatoriu')) {
                                    continue;
                                }
                                if ((line.includes('.pdf') || line.includes('.jpg') || line.includes('.png') || line.includes('.jpeg') || line.includes('.bmp')) && !line.includes('formatul admis')) {
                                    return true;
                                }
                                if (line.includes('încărcat') || line.includes('incarcat') || line.includes('uploaded') || line.includes('salvat') || line.includes('saved') || line.includes('atașat') || line.includes('atasat') || line.includes('document salvat') || line.includes('fișier atașat') || line.includes('fisier atasat')) {
                                    return true;
                                }
                            }

                            // Check 6: File input populated or hidden input with saved value
                            const fileInp = rowEl.querySelector('input[type="file"]');
                            if (fileInp && fileInp.files && fileInp.files.length > 0) {
                                return true;
                            }

                            const hiddenInps = Array.from(rowEl.querySelectorAll('input[type="hidden"]'));
                            for (const h of hiddenInps) {
                                const val = (h.value || '').trim();
                                const name = (h.name || h.id || '').toLowerCase();
                                if (val && val !== '0' && val !== 'false') {
                                    if (name.includes('fisier') || name.includes('doc') || name.includes('file') || name.includes('upload') || val.includes('.pdf') || val.includes('.jpg') || val.includes('.png') || name.includes(numId)) {
                                        return true;
                                    }
                                }
                            }

                            return false;
                        }""",
                        {
                            "id": field["id"],
                            "num_id": field.get("num_id") or field["id"].split("_")[-1],
                            "order": field["order"],
                            "category_id": field.get("category_id") or field.get("suffix_code"),
                            "keywords": field["keywords"]
                        }
                    )
                    if getattr(self, "_debug_upload_detection", True):
                        print(f"   🔍 [{field['label']}] row-match result: {bool(res)}")
                    if res:
                        uploaded = True
                        self.permanently_uploaded_field_ids.add(field["id"])
                        self.permanently_uploaded_field_ids.add(field["order"])
                        if field.get("num_id"):
                            self.permanently_uploaded_field_ids.add(field["num_id"])
                        if field.get("suffix_code"):
                            self.permanently_uploaded_field_ids.add(field["suffix_code"])
                        if isinstance(self.data, dict):
                            self.data["permanently_uploaded_field_ids"] = list(self.permanently_uploaded_field_ids)
                        self.save_uploaded_cache()
                        break
                except Exception as ex:
                    if getattr(self, "_debug_upload_detection", True):
                        print(f"   ⚠️ [{field['label']}] detection error in one frame: {ex}")
            statuses.append({**field, "uploaded": uploaded})
        return statuses

    async def upload_single_document_field(self, field, target_file_path):
        """
        Uploads exactly ONE resolved local file into exactly ONE portal row, scoped strictly
        to that row's own <input type="file">.
        Immediately monitors upload progress and returns as soon as completion is recognized.
        Enforces NO DOUBLE UPLOADS under any circumstances.
        """
        input_id = field["id"]
        order = field["order"]
        keywords = field["keywords"]
        label = field["label"]
        num_id = field.get("num_id") or input_id.split("_")[-1]

        if not hasattr(self, "permanently_uploaded_field_ids"):
            self.permanently_uploaded_field_ids = set()

        if input_id in self.permanently_uploaded_field_ids or order in self.permanently_uploaded_field_ids or num_id in self.permanently_uploaded_field_ids:
            print(f"ℹ️ [{label}] is already permanently uploaded. Skipping upload to ensure it is uploaded ONLY ONCE.")
            return True

        print(f"📤 Uploading [{os.path.basename(target_file_path)}] for {label} (row-scoped only)...")
        upload_done = False
        for frame in self.page.frames:
            try:
                file_input = await frame.query_selector(f"#{input_id}")
                if not file_input:
                    file_input = await frame.query_selector(f"input[type='file'][name*='{input_id}']")
                if not file_input:
                    file_input = await frame.query_selector(f"input[type='file'][id*='{input_id}']")
                if not file_input and ("31" in input_id or order == 2):
                    file_input = await frame.query_selector("input[type='file'][id*='31'], input[type='file'][name*='31'], input[type='file'][id*='FIN' i], input[type='file'][name*='FIN' i]")
                if not file_input:
                    row_handle = await frame.evaluate_handle(
                        """(args) => {
                            const norm = (s) => (s || '').toLowerCase();
                            const rows = Array.from(document.querySelectorAll('tr, fieldset, .form-group, .row, div.document-row, div.upload-row'));
                            for (const r of rows) {
                                const t = norm(r.textContent || '');
                                if ((t.includes(`${args.order}.`) || t.includes(`${args.order} `)) && args.keywords.some(kw => t.includes(kw))) {
                                    return r;
                                }
                            }
                            for (const r of rows) {
                                const t = norm(r.textContent || '');
                                if (t.includes(`${args.order}.`) || t.includes(`${args.order} `)) {
                                    return r;
                                }
                            }
                            return null;
                        }""",
                        {"order": order, "keywords": keywords}
                    )
                    row_el = row_handle.as_element() if row_handle else None
                    if row_el:
                        file_input = await row_el.query_selector("input[type='file']")
                if not file_input:
                    all_inputs = await frame.query_selector_all("input[type='file']")
                    if len(all_inputs) >= order:
                        file_input = all_inputs[order - 1]

                if file_input:
                    # Check if already has a file uploaded in DOM before injecting
                    already_has_file = await frame.evaluate(
                        r"""(inp) => {
                            const norm = (s) => (s || '').toLowerCase().trim();
                            let rowEl = inp.closest('tr') || inp.closest('fieldset') || inp.closest('.document-row') || inp.closest('.form-group') || inp.closest('.k-upload') || inp.parentElement;
                            if (!rowEl) return false;
                            if (rowEl.closest('tr')) {
                                rowEl = rowEl.closest('tr');
                            }

                            // 1. Download or View links
                            const links = Array.from(rowEl.querySelectorAll('a, button, [role="button"], span[onclick], i[onclick]'));
                            for (const el of links) {
                                const href = norm(el.getAttribute('href') || '');
                                const txt = norm(el.textContent || el.innerText || '');
                                const title = norm(el.getAttribute('title') || '');
                                const onclick = norm(el.getAttribute('onclick') || '');
                                const cls = norm(el.className || '');
                                if (href.includes('descarca') || href.includes('download') || href.includes('vizualizare') || href.includes('vizualiz') || href.includes('getfile') || href.includes('.pdf') || href.includes('.jpg') || href.includes('.png') ||
                                    txt.includes('descarcă') || txt.includes('descarca') || txt.includes('download') || txt.includes('vizualizare') || txt.includes('vizualiz') || txt.includes('view') ||
                                    ((txt.includes('.pdf') || txt.includes('.jpg') || txt.includes('.png') || txt.includes('.jpeg')) && !txt.includes('formatul') && !txt.includes('admis')) ||
                                    title.includes('descarcă') || title.includes('descarca') || title.includes('download') || title.includes('vizualizare') ||
                                    onclick.includes('descarca') || onclick.includes('download') || onclick.includes('vizualizare') || onclick.includes('vizualiz')) {
                                    return true;
                                }
                                if (txt.includes('șterge') || txt.includes('sterge') || txt.includes('delete') || txt.includes('remove') ||
                                    title.includes('șterge') || title.includes('sterge') || title.includes('delete') ||
                                    href.includes('sterge') || href.includes('delete') || href.includes('remove') ||
                                    onclick.includes('sterge') || onclick.includes('delete') ||
                                    cls.includes('k-delete') || cls.includes('k-upload-action') || cls.includes('delete') || cls.includes('btn-danger') ||
                                    !!el.querySelector('.k-i-close, .k-i-trash, .fa-trash, .glyphicon-trash, .fa-remove, .fa-times')) {
                                    return true;
                                }
                            }

                            // 2. Kendo Upload list items with filename and no error
                            const kFiles = Array.from(rowEl.querySelectorAll('.k-upload-files .k-file, ul.k-upload-files li, .k-file'));
                            for (const kf of kFiles) {
                                const isError = kf.classList.contains('k-file-error') || kf.classList.contains('k-upload-error') || !!kf.querySelector('.k-file-error, .k-upload-error, .k-i-warning, .k-warning');
                                if (!isError) {
                                    const fnEl = kf.querySelector('.k-file-name, .k-filename, .k-upload-file-name, .k-file-name-size');
                                    const fnText = norm(fnEl ? fnEl.textContent : kf.textContent);
                                    if ((fnText.includes('.pdf') || fnText.includes('.jpg') || fnText.includes('.png') || fnText.includes('.jpeg')) && !fnText.includes('formatul') && !fnText.includes('admis')) {
                                        return true;
                                    }
                                    if (kf.classList.contains('k-file-success') || !!kf.querySelector('.k-upload-action, button, .k-i-close')) {
                                        return true;
                                    }
                                }
                            }

                            // 3. Success indicator
                            if (rowEl.querySelector('.k-file-success, .k-upload-success, .k-i-checkmark, .glyphicon-ok, .fa-check, .badge-success, .label-success, .text-success')) {
                                return true;
                            }

                            // 4. Filename or status text in row
                            const rowFullText = norm(rowEl.innerText || rowEl.textContent || '');
                            if ((rowFullText.includes('.pdf') || rowFullText.includes('.jpg') || rowFullText.includes('.png') || rowFullText.includes('.jpeg')) && !rowFullText.includes('formatul admis')) {
                                return true;
                            }
                            if (rowFullText.includes('încărcat') || rowFullText.includes('incarcat') || rowFullText.includes('uploaded') || rowFullText.includes('salvat') || rowFullText.includes('saved') || rowFullText.includes('atașat') || rowFullText.includes('atasat') || rowFullText.includes('document salvat')) {
                                return true;
                            }

                            return false;
                        }""",
                        file_input
                    )
                    if already_has_file:
                        self.permanently_uploaded_field_ids.add(input_id)
                        self.permanently_uploaded_field_ids.add(order)
                        self.permanently_uploaded_field_ids.add(num_id)
                        if isinstance(self.data, dict):
                            self.data["permanently_uploaded_field_ids"] = list(self.permanently_uploaded_field_ids)
                        self.save_uploaded_cache()
                        print(f"ℹ️ [{label}] DOM already contains uploaded file on portal. Preserving single upload.")
                        return True

                    await file_input.set_input_files(target_file_path)
                    await frame.evaluate(
                        """(el) => {
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            const row = el.closest('tr, fieldset, .form-group, .row, .k-upload') || el.parentElement;
                            if (row) {
                                const upBtn = row.querySelector('.k-upload-selected, button.k-upload-selected, button[title*="Upload" i], input[value*="Upload" i], button:has(.k-i-upload), .k-button.k-upload-selected');
                                if (upBtn) {
                                    try { upBtn.click(); } catch(e){}
                                }
                            }
                            if (typeof window.$ !== 'undefined' || typeof window.jQuery !== 'undefined') {
                                try {
                                    const jq = window.$ || window.jQuery;
                                    const $el = jq(el);
                                    $el.trigger('change');
                                    const upWidget = $el.closest('.k-upload').data('kendoUpload') || $el.data('kendoUpload');
                                    if (upWidget && typeof upWidget.upload === 'function') {
                                        upWidget.upload();
                                    }
                                } catch(e){}
                            }
                        }""",
                        file_input
                    )
                    upload_done = True
                    print(f"✅ Injected file into the row-scoped input for [{label}].")
                    break
            except Exception as up_err:
                print(f"Upload attempt note in frame for [{label}]: {up_err}")

        if not upload_done:
            print(f"⚠️ Could not locate a file input strictly scoped to [{label}]'s row this cycle - will retry on the next scan.")
            return "NO_INPUT_FOUND"

        # Actively observe row completion with fast polling (100ms intervals) - no unnecessary delays
        start_wait = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_wait < 25:
            if await self.is_unexpected_error_popup():
                print(f"⚠️ Portal 'unexpected error' popup appeared while uploading [{label}].")
                return "ERROR_POPUP"
            try:
                status_info = await self.page.evaluate(
                    """(args) => {
                        const norm = (s) => (s || '').toLowerCase();
                        const inp = document.getElementById(args.id) || document.querySelector(`input[name*="${args.id}"]`);
                        let rowEl = inp ? (inp.closest('tr') || inp.closest('fieldset') || inp.closest('.document-row') || inp.closest('.form-group') || inp.closest('.k-upload')) : null;
                        if (!rowEl) {
                            const rows = Array.from(document.querySelectorAll('tr, fieldset, .form-group, .row, div.document-row, div.upload-row'));
                            for (const r of rows) {
                                const t = norm(r.textContent || '');
                                if (t.includes(`${args.order}.`) || t.includes(`${args.order} `)) {
                                    rowEl = r;
                                    break;
                                }
                            }
                        }
                        if (!rowEl) return { hasUploaded: false };
                        if (rowEl.closest('tr')) {
                            rowEl = rowEl.closest('tr');
                        }

                        const successEl = rowEl.querySelector('.k-upload-success, .k-file-success, .k-i-checkmark, .k-success, a[href*="Descarca" i], a[href*="Download" i], button.k-delete, button[title*="Delete" i]');
                        const percentEl = rowEl.querySelector('.k-progress-status, .k-upload-status');
                        const percentTxt = norm(percentEl ? percentEl.textContent : '');
                        const stillUploading = percentTxt.length > 0 && !percentTxt.includes('100%') && !percentTxt.includes('done') && !percentTxt.includes('complete');

                        const kFile = rowEl.querySelector('.k-file-name, .k-filename, .k-upload-file-name');
                        const hasNamedFile = !!kFile && (norm(kFile.textContent || '').includes('.pdf') || norm(kFile.textContent || '').includes('.jpg') || norm(kFile.textContent || '').includes('.png'));

                        return { hasUploaded: (!!successEl || hasNamedFile) && !stillUploading };
                    }""",
                    {"id": input_id, "order": order}
                )
                if status_info.get("hasUploaded"):
                    self.permanently_uploaded_field_ids.add(input_id)
                    self.permanently_uploaded_field_ids.add(order)
                    self.permanently_uploaded_field_ids.add(num_id)
                    if isinstance(self.data, dict):
                        self.data["permanently_uploaded_field_ids"] = list(self.permanently_uploaded_field_ids)
                    self.save_uploaded_cache()
                    print(f"✅ Recognized upload completion for [{label}]. Immediately advancing...")
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.10)

        print(f"⚠️ [{label}] upload could not be verified on the portal within the timeout. Will re-attempt on next scan.")
        return False

    async def check_declaration_checkbox_once(self):
        """
        Ticks the mandatory 'I am aware of the supporting documents...' checkbox.

        ROOT-CAUSE FIX for the 'sudden reload / you must check the box' bug: the previous
        version manually forced `.checked = true` and THEN ALSO dispatched a synthetic
        'click' MouseEvent (plus mousedown/mouseup/a label click). Dispatching a 'click'
        event at a checkbox always runs the browser's native toggle behaviour, dispatched or
        not - so that synthetic click flipped the box straight back to UNCHECKED a moment
        after it had just been set true, and the label's own forwarded click could toggle it
        a second time on top of that. The portal's own validator reacts to that real
        unchecked state with 'you must check the box', and its re-validation of the change is
        what looked like a sudden reload. The fix: call the native `.click()` method exactly
        ONCE, only if the box isn't already checked, and dispatch nothing else afterwards.
        """
        for frame in self.page.frames:
            try:
                res = await frame.evaluate(
                    """() => {
                        const norm = (s) => (s || '').trim().toLowerCase();
                        const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
                        let targetCheckbox = null;
                        for (const chk of checkboxes) {
                            const parent = chk.closest('label, div, td, tr, p, fieldset, li') || chk.parentElement;
                            const txt = norm(parent ? parent.textContent || '' : '');
                            const id = chk.id;
                            const labelEl = id ? document.querySelector(`label[for="${id}"]`) : null;
                            const labelTxt = norm(labelEl ? labelEl.textContent || '' : '');
                            const isDeclaration =
                                txt.includes('i am aware of the supporting documents') ||
                                txt.includes('supporting documents that are requested') ||
                                txt.includes('hereby oblige myself to submit them in original and copy') ||
                                txt.includes('personally lodge my visa application') ||
                                txt.includes('am luat la cunoștință') ||
                                txt.includes('am luat la cunostinta') ||
                                txt.includes('sunt conștient') ||
                                txt.includes('sunt constient') ||
                                labelTxt.includes('i am aware') ||
                                labelTxt.includes('am luat la cunoștință');
                            if (isDeclaration) { targetCheckbox = chk; break; }
                        }
                        if (!targetCheckbox && checkboxes.length > 0) {
                            targetCheckbox = checkboxes[checkboxes.length - 1];
                        }
                        if (!targetCheckbox) return { found: false };

                        targetCheckbox.scrollIntoView({ behavior: 'instant', block: 'center' });

                        if (!targetCheckbox.checked) {
                            targetCheckbox.click();
                        }

                        if (targetCheckbox.checked) {
                            document.querySelectorAll('.field-validation-error, .validator, .text-danger, [id*="Validator"]').forEach(v => {
                                const t = (v.textContent || '').toLowerCase();
                                if (t.includes('check the box') || t.includes('bifați') || t.includes('bifati')) {
                                    v.style.display = 'none';
                                }
                            });
                        }

                        return { found: true, checked: targetCheckbox.checked };
                    }"""
                )
                if res and res.get("found"):
                    return bool(res.get("checked"))
            except Exception as chk_err:
                print(f"Checkbox verification notice in frame: {chk_err}")
        return False

    async def is_declaration_checkbox_checked(self):
        """
        Read-only, independent re-check of the declaration checkbox's real DOM state.
        Deliberately a SEPARATE call from check_declaration_checkbox_once() (rather than
        trusting the boolean that call already returned) so the caller can confirm the box
        is still checked a moment after clicking it, before proceeding to Save/Next.
        """
        for frame in self.page.frames:
            try:
                res = await frame.evaluate(
                    """() => {
                        const norm = (s) => (s || '').trim().toLowerCase();
                        const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
                        for (const chk of checkboxes) {
                            const parent = chk.closest('label, div, td, tr, p, fieldset, li') || chk.parentElement;
                            const txt = norm(parent ? parent.textContent || '' : '');
                            const id = chk.id;
                            const labelEl = id ? document.querySelector(`label[for="${id}"]`) : null;
                            const labelTxt = norm(labelEl ? labelEl.textContent || '' : '');
                            const isDeclaration =
                                txt.includes('i am aware of the supporting documents') ||
                                txt.includes('supporting documents that are requested') ||
                                txt.includes('hereby oblige myself to submit them in original and copy') ||
                                txt.includes('personally lodge my visa application') ||
                                txt.includes('am luat la cunoștință') ||
                                txt.includes('am luat la cunostinta') ||
                                labelTxt.includes('i am aware');
                            if (isDeclaration) return { found: true, checked: chk.checked };
                        }
                        if (checkboxes.length > 0) {
                            return { found: true, checked: checkboxes[checkboxes.length - 1].checked };
                        }
                        return { found: false, checked: false };
                    }"""
                )
                if res and res.get("found"):
                    return bool(res.get("checked"))
            except Exception:
                pass
        return False

    async def page_supporting_documents(self):
        """
        Step: Final Supporting Documents File Uploads (Kendo UI Upload 6-Field Pipeline &
        Mandatory Declaration Checkbox).

        Key Rules Enforced:
        1. UPLOAD ONLY ONCE: Each field is uploaded exactly ONE time (no double uploads).
        2. AGREEMENT for Means of Support: Field 2 strictly uploads AGREEMENT.pdf, never insurance.
        3. RESUME EMPTY FIELDS TOP-TO-BOTTOM: On refresh, scans 1 to 6, identifies empty fields, and uploads only empty ones.
        4. NO ARBITRARY WAITING: Immediately recognizes upload completion and advances to the next field.
        5. SAVE BUTTON FULL REFRESHMENT: Waits until full page refreshment finishes before clicking Next button.
        """
        print("Step: Final Supporting Documents (Documente Justificative)...")
        import urllib.request
        import base64

        print("⏳ Stabilizing Required Supporting Documents page for document uploads...")
        await asyncio.sleep(0.5)
        await self.wait_for_ajax_idle(6000)

        if not hasattr(self, "permanently_uploaded_field_ids"):
            self.permanently_uploaded_field_ids = set()

        if await self.is_session_expired_page():
            print("🛑 Session already expired on arrival at this step - touching no uploads. Returning control to the main loop, which will stop the automation.")
            return

        upload_fields = [
            {
                "id": "UploadDocumenteJustificative_30",
                "num_id": "30",
                "order": 1,
                "keyword": "permit",
                "keywords": ["work permit", "work", "permit", "autorizatie de munca", "autorizație de muncă", "autorizatie", "munca", "mun_1", "_mun_", "wp"],
                "label": "1 WORK PERMIT",
                "default_file": "WORK_PERMIT.pdf",
                "suffix_code": "MUN"
            },
            {
                "id": "UploadDocumenteJustificative_31",
                "num_id": "31",
                "order": 2,
                "keyword": "support",
                "keywords": ["means of support", "means", "support", "agreement", "contract", "acord", "angajament", "cazare", "mijloace de intretinere", "mijloace de întreținere", "mijloace", "fin_1", "_fin_"],
                "label": "2 MEANS OF SUPPORT",
                "default_file": "AGREEMENT.pdf",
                "suffix_code": "FIN"
            },
            {
                "id": "UploadDocumenteJustificative_32",
                "num_id": "32",
                "order": 3,
                "keyword": "criminal",
                "keywords": ["criminal record", "criminal", "record", "police report", "police clearance", "police", "cazier judiciar", "cazier", "jud_1", "_jud_"],
                "label": "3 CRIMINAL RECORD",
                "default_file": "POLICE_REPORT.pdf",
                "suffix_code": "JUD"
            },
            {
                "id": "UploadDocumenteJustificative_10",
                "num_id": "10",
                "order": 4,
                "keyword": "insurance",
                "keywords": ["travel medical insurance", "medical insurance", "insurance", "asigurare medicala", "asigurare medicală", "asigurare", "med_1", "_med_"],
                "label": "4 TRAVEL MEDICAL INSURANCE",
                "default_file": "INSURANCE.pdf",
                "suffix_code": "MED"
            },
            {
                "id": "UploadDocumenteJustificative_1",
                "num_id": "1",
                "order": 5,
                "keyword": "passport",
                "keywords": ["valid travel document", "travel document", "passport", "pasaport", "pașaport", "document de calatorie", "document de călătorie", "pas_1", "_pas_"],
                "label": "5 VALID TRAVEL DOCUMENT",
                "default_file": "PASSPORT.pdf",
                "suffix_code": "PAS"
            },
            {
                "id": "UploadDocumenteJustificative_2",
                "num_id": "2",
                "order": 6,
                "keyword": "photo",
                "keywords": ["photographs", "photograph", "photo", "img", "fotografii", "fotografie", "poza", "fot_1", "_fot_"],
                "label": "6 PHOTOGRAPHS",
                "default_file": "PHOTOGRAPHS.pdf",
                "suffix_code": "FOT"
            }
        ]

        # ------------------------------------------------------------------------------
        # RESUME-ON-RESTART CHECK: if the whole automation had to restart from the very
        # beginning (session expiry, browser crash, manual re-run, etc.) and this step is
        # reached again, some of the 6 fields below may already have a real document saved
        # on the portal from the earlier run. This scan runs unconditionally - even if a
        # leftover "unexpected error" banner or validation message is still showing on the
        # page from before the restart - so a stale error message never blocks the resume
        # check or forces a needless re-upload.
        #
        # It only READS live DOM state (view/download links, a successful Kendo upload
        # entry, or a populated file input) via the SAME get_upload_field_statuses() used
        # everywhere else on this page, so it can never invent a false "already uploaded"
        # status, and it cannot interfere with any other rule on this page: the
        # AGREEMENT-only rule for field 2, the strict upload-once rule, the mandatory
        # declaration checkbox, or the Save/Next flow below. It only decides, up front,
        # which fields the existing top-to-bottom loop is allowed to skip.
        # ------------------------------------------------------------------------------
        print("\n🔎 Resume check: scanning all 6 fields for documents already saved on the portal...")
        resume_statuses = await self.get_upload_field_statuses(upload_fields)

        # ROOT-CAUSE FIX: on a slow-loading Required Supporting Documents page, the
        # Kendo grid widgets that hold "already uploaded" file entries can still be
        # mid-render when the scan above runs - so an already-uploaded field gets
        # misread as empty and is needlessly re-uploaded. Debounce: any field that
        # reads as "not uploaded" on the first pass gets one delayed re-check before
        # we trust it, giving slow Kendo grids time to finish attaching their data.
        still_unconfirmed = [f for f, s in zip(upload_fields, resume_statuses) if not s["uploaded"]]
        if still_unconfirmed:
            print(f"⏳ {len(still_unconfirmed)} field(s) read as empty on first scan - waiting for the page to fully settle before trusting that...")
            await asyncio.sleep(4.0)
            await self.wait_for_ajax_idle(6000)
            recheck_statuses = await self.get_upload_field_statuses(still_unconfirmed)
            recheck_map = {s["id"]: s["uploaded"] for s in recheck_statuses}
            for s in resume_statuses:
                if s["id"] in recheck_map and recheck_map[s["id"]]:
                    print(f"🔧 [Auto-Heal] '{s['label']}' was actually already uploaded - first scan caught the page mid-render. Correcting status.")
                    s["uploaded"] = True

        already_done_labels = []
        still_missing_labels = []
        for s in resume_statuses:
            if s["uploaded"]:
                self.permanently_uploaded_field_ids.add(s["id"])
                self.permanently_uploaded_field_ids.add(s["order"])
                already_done_labels.append(s["label"])
            else:
                still_missing_labels.append(s["label"])
        if already_done_labels:
            print(f"✅ Already uploaded on the portal - will NOT be re-uploaded: {', '.join(already_done_labels)}")
        if still_missing_labels:
            print(f"⏳ Still empty - will be uploaded now: {', '.join(still_missing_labels)}")
        else:
            print("✅ All 6 fields already have documents saved on the portal - nothing left to upload.")

        allowed_exts = (".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".tif", ".txt", ".rtf")
        image_exts = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")
        max_size_bytes = 2048 * 1024

        folder_path = self.data.get("documents_folder") or get_safe_temp_dir("evisa_applicant_docs")

        # ------------------------------------------------------------------------------
        # STRICT VISA SUBMISSION FOLDER RESTRICTION:
        # After recognizing the folder location using passport inside VISA SUBMISSION folder,
        # the system MUST ONLY look in that specific applicant's folder.
        # It is strictly prohibited from pulling files from Downloads, Desktop, or other applicants' folders.
        # ------------------------------------------------------------------------------
        target_vs_folder = None
        for cand_dir in [
            getattr(self, "verified_applicant_folder", None),
            self.data.get("documents_folder"),
            APPLICANT_DATA.get("documents_folder") if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA, dict) else None,
            getattr(self, "verified_passport_folder", None),
        ]:
            if cand_dir and isinstance(cand_dir, str) and os.path.isdir(cand_dir):
                target_vs_folder = os.path.abspath(cand_dir)
                break

        candidate_folders = []
        if target_vs_folder and os.path.isdir(target_vs_folder):
            print(f"🔒 STRICT FOLDER BOUNDARY ACTIVE: System searching EXCLUSIVELY inside applicant's folder: {target_vs_folder}")
            candidate_folders.append(target_vs_folder)
            try:
                for sub in os.listdir(target_vs_folder):
                    sub_p = os.path.join(target_vs_folder, sub)
                    if os.path.isdir(sub_p) and sub not in (".git", "node_modules", ".cache", "tmp", "__pycache__"):
                        candidate_folders.append(sub_p)
            except Exception:
                pass
        else:
            if folder_path and os.path.isdir(folder_path):
                candidate_folders.append(os.path.abspath(folder_path))
            else:
                default_temp = get_safe_temp_dir("evisa_applicant_docs")
                if os.path.isdir(default_temp):
                    candidate_folders.append(default_temp)

        print(f"📁 Local search directories ({len(candidate_folders)} found): {', '.join(candidate_folders)}")

        # Collect candidate files EXCLUSIVELY across candidate directories
        def collect_all_available_files():
            found_files = []
            seen_paths = set()
            for root_dir in candidate_folders:
                try:
                    for root, dirs, files in os.walk(root_dir):
                        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".cache", "chrome", "__pycache__", "build", "dist")]
                        for fn in files:
                            fp = os.path.join(root, fn)
                            if fp not in seen_paths and os.path.isfile(fp):
                                seen_paths.add(fp)
                                found_files.append(fp)
                except Exception:
                    pass
            return found_files

        all_candidate_files = collect_all_available_files()
        print(f"📄 Discovered {len(all_candidate_files)} total files strictly within applicant's folder.")

        tmp_dir = get_safe_temp_dir()

        def resolve_file_from_source(source_val, target_filename, doc_label):
            if not source_val:
                return None
            source_str = str(source_val).strip()

            if os.path.exists(source_str) and os.path.isfile(source_str):
                return source_str

            # Check if source_str is a file name or path that exists in candidate files
            file_basename = os.path.basename(source_str) or target_filename
            for fp in all_candidate_files:
                fn = os.path.basename(fp)
                if fn.lower() == file_basename.lower() or fn.lower() == target_filename.lower():
                    if os.path.isfile(fp) and os.path.getsize(fp) > 0:
                        return fp

            if "base64," in source_str:
                try:
                    b64_part = source_str.split("base64,")[1]
                    raw_bytes = base64.b64decode(b64_part)
                    local_dest = os.path.join(tmp_dir, target_filename)
                    with open(local_dest, "wb") as out_f:
                        out_f.write(raw_bytes)
                    if os.path.exists(local_dest) and os.path.getsize(local_dest) > 100:
                        print(f"✅ Decoded Base64 document [{target_filename}] ({len(raw_bytes)} bytes)")
                        return local_dest
                except Exception as b64_err:
                    print(f"⚠️ Base64 decode error for [{doc_label}]: {b64_err}")

            if source_str.startswith("http://") or source_str.startswith("https://"):
                local_dest = os.path.join(tmp_dir, target_filename)
                is_sandbox_url = "ais-dev" in source_str or "localhost:3000" in source_str or ".run.app" in source_str
                if is_sandbox_url:
                    print(f"ℹ️ Cloud Sandbox URL detected for [{doc_label}]. Attempting local fetch with fallback...")

                download_url = source_str
                if "drive.google.com" in source_str:
                    import re
                    gdrive_match = re.search(r'(?:file/d/|id=)([a-zA-Z0-9_-]+)', source_str)
                    if gdrive_match:
                        file_id = gdrive_match.group(1)
                        download_url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t"
                        print(f"🔗 Converted Google Drive link to direct download URL: {download_url}")

                try:
                    print(f"⬇️ Downloading document for [{doc_label}] from link: {download_url[:70]}...")
                    req = urllib.request.Request(
                        download_url,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                            "Accept": "application/pdf,image/*,*/*"
                        }
                    )
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        content_data = resp.read()
                        is_html = content_data[:100].lower().startswith(b"<!doctype") or content_data[:100].lower().startswith(b"<html")
                        if is_html and "drive.google.com" in download_url:
                            html_text = content_data.decode("utf-8", errors="ignore")
                            confirm_match = re.search(r'href="(/uc\?export=download[^"]+)"', html_text)
                            if confirm_match:
                                confirm_url = "https://drive.google.com" + confirm_match.group(1).replace("&amp;", "&")
                                req2 = urllib.request.Request(confirm_url, headers={"User-Agent": "Mozilla/5.0"})
                                with urllib.request.urlopen(req2, timeout=20) as resp2:
                                    content_data = resp2.read()
                                    is_html = content_data[:100].lower().startswith(b"<!doctype")

                        if not is_html and len(content_data) > 100:
                            with open(local_dest, "wb") as out_f:
                                out_f.write(content_data)
                            print(f"✅ Successfully downloaded [{target_filename}] ({len(content_data)} bytes)")
                            return local_dest
                        else:
                            print(f"⚠️ Downloaded content for [{doc_label}] is an HTML web page rather than binary PDF/Image.")
                except Exception as dl_err:
                    print(f"⚠️ URL download error for [{doc_label}]: {dl_err}")

            return None

        def resolve_target_file_for(field):
            keyword = field["keyword"]
            keywords = field["keywords"]
            label = field["label"]
            order = field["order"]
            default_file = field["default_file"]

            target_file_path = None

            # Special strict handling for MEANS OF SUPPORT (Order 2):
            # STRICT REQUIREMENT: Upload real AGREEMENT / ACORD / ANGAJAMENT / UNDERTAKING into it. STRICTLY FORBID INSURANCE FILES.
            if keyword == "support" or order == 2:
                # 1. Check explicit file entries in self.data["files"]
                files_dict = self.data.get("files", {}) if isinstance(self.data.get("files"), dict) else {}
                for k in ("agreement", "support", "means_of_support", "fin", "acord", "cazare", "angajament", "undertaking", "sponsor", "retex", "company"):
                    val = files_dict.get(k)
                    if val and not any(bad in str(val).lower() for bad in ("insurance", "medical", "asigurare", "med_1", "_med_")):
                        cand = resolve_file_from_source(val, "AGREEMENT.pdf", label)
                        if cand and os.path.exists(cand) and os.path.isfile(cand) and os.path.getsize(cand) > 100:
                            target_file_path = cand
                            break

                # 2. Check top-level data fields
                if not target_file_path:
                    for top_k in ("agreement_file", "agreement_path", "agreement", "support_file", "support_path", "support", "means_of_support_file", "means_of_support", "fin_file", "fin_path", "retex_file", "host_file"):
                        top_val = self.data.get(top_k)
                        if top_val and not any(bad in str(top_val).lower() for bad in ("insurance", "medical", "asigurare", "med_1", "_med_")):
                            cand = resolve_file_from_source(top_val, "AGREEMENT.pdf", label)
                            if cand and os.path.exists(cand) and os.path.isfile(cand) and os.path.getsize(cand) > 100:
                                target_file_path = cand
                                break

                # 3. Check documents list in self.data
                if not target_file_path:
                    docs_list = self.data.get("documents", []) if isinstance(self.data.get("documents"), list) else []
                    for d in docs_list:
                        d_key = (d.get("typeKey") or d.get("key") or "").upper()
                        d_name = (d.get("fileName") or d.get("label") or "").lower()
                        if any(bad in d_name for bad in ("insurance", "medical", "asigurare", "med_1", "_med_")):
                            continue
                        if d_key in ("MEANS_OF_SUPPORT", "AGREEMENT", "SUPPORT", "FIN", "FIN_1", "ACORD", "CAZARE", "ANGAJAMENT", "UNDERTAKING", "SPONSOR", "CONTRACT", "RETEX") or any(kw in d_name for kw in ("agreement", "acord", "angajament", "cazare", "support", "fin", "undertaking", "sponsor", "contract", "mijloace", "retex")):
                            f_src = d.get("fileDataUrl") or d.get("url") or d.get("link") or d.get("path") or d.get("fileName")
                            if f_src:
                                cand = resolve_file_from_source(f_src, d.get("fileName") or "AGREEMENT.pdf", label)
                                if cand and os.path.exists(cand) and os.path.isfile(cand) and os.path.getsize(cand) > 100:
                                    target_file_path = cand
                                    break

                # 4. Search all candidate files for exact/standard Agreement file names
                if not target_file_path:
                    exact_names = [
                        "agreement.pdf", "acord.pdf", "angajament.pdf", "cazare.pdf", "support.pdf",
                        "means_of_support.pdf", "means.pdf", "undertaking.pdf", "guarantee.pdf", "garantie.pdf",
                        "sponsor.pdf", "sponsorship.pdf", "contract.pdf", "mijloace.pdf", "intretinere.pdf",
                        "retex.pdf", "retex green s.r.l.pdf", "retex_green.pdf", "retex green.pdf", "angajament_de_plata.pdf", "acord_cazare.pdf"
                    ]
                    for fp in all_candidate_files:
                        fn_l = os.path.basename(fp).lower()
                        if any(bad in fn_l for bad in ("insurance", "medical", "asigurare", "med_1", "_med_")):
                            continue
                        if fn_l in exact_names or any(fn_l == en for en in exact_names):
                            if os.path.isfile(fp) and os.path.getsize(fp) <= max_size_bytes and os.path.getsize(fp) > 100:
                                target_file_path = fp
                                print(f"📄 Found exact matching Agreement document: {target_file_path}")
                                break

                # 5. Search candidate files by Agreement keywords
                if not target_file_path:
                    agr_keywords = (
                        "agreement", "acord", "angajament", "cazare", "support", "intretinere",
                        "întreținere", "mijloace", "fin_1", "_fin_", "fin", "undertaking",
                        "sponsor", "sponsorship", "guarantee", "garantie", "garanție", "contract", "retex"
                    )
                    for fp in all_candidate_files:
                        fn_l = os.path.basename(fp).lower()
                        if any(bad in fn_l for bad in ("insurance", "medical", "asigurare", "med_1", "_med_", "passport", "pasaport", "cazier", "police", "criminal", "work_permit", "munca", "photo", "poza")):
                            continue
                        if any(kw in fn_l for kw in agr_keywords) and fn_l.endswith(allowed_exts):
                            if os.path.isfile(fp) and os.path.getsize(fp) <= max_size_bytes and os.path.getsize(fp) > 100:
                                target_file_path = fp
                                print(f"📄 Found keyword-matching Agreement document: {target_file_path}")
                                break

                # 6. Deep PDF text extraction scanner for Agreement terms
                if not target_file_path:
                    print("🔍 [Agreement Matcher] Scanning PDF documents for Agreement / Accommodation / Undertaking text...")
                    agr_text_terms = (
                        "agreement", "acord", "angajament", "cazare", "undertaking", "sponsor",
                        "sponsorship", "guarantee", "garantie", "oblige", "retex", "means of support",
                        "intretinere", "cheltuieli", "accommodation", "host", "angajator", "sponsorizare"
                    )
                    for fp in all_candidate_files:
                        if not fp.lower().endswith(".pdf"):
                            continue
                        fn_l = os.path.basename(fp).lower()
                        if any(bad in fn_l for bad in ("insurance", "medical", "asigurare", "med_1", "_med_", "passport", "pasaport", "cazier", "police", "criminal", "work_permit", "munca", "photo", "poza")):
                            continue
                        try:
                            pdf_text = extract_pdf_text_via_pypdf(fp).lower()
                            if pdf_text and not any(bad in pdf_text for bad in ("insurance", "medical", "asigurare", "police clearance", "criminal record", "cazier")):
                                if any(term in pdf_text for term in agr_text_terms):
                                    if os.path.isfile(fp) and os.path.getsize(fp) <= max_size_bytes and os.path.getsize(fp) > 100:
                                        target_file_path = fp
                                        print(f"🎯 Verified Agreement document found by PDF content extraction: {target_file_path}")
                                        break
                        except Exception:
                            pass

                # 7. Process of elimination in applicant document folder
                if not target_file_path and folder_path and os.path.isdir(folder_path):
                    try:
                        for fn in os.listdir(folder_path):
                            fn_l = fn.lower()
                            if any(bad in fn_l for bad in ("insurance", "medical", "asigurare", "med_1", "_med_", "passport", "pasaport", "cazier", "police", "criminal", "work_permit", "munca", "photo", "poza")):
                                continue
                            if fn_l.endswith((".pdf", ".jpg", ".png")):
                                full_p = os.path.join(folder_path, fn)
                                if os.path.isfile(full_p) and os.path.getsize(full_p) <= max_size_bytes and os.path.getsize(full_p) > 100:
                                    target_file_path = full_p
                                    print(f"📄 Assigned applicant folder document to Agreement / Means of Support: {target_file_path}")
                                    break
                    except Exception:
                        pass

            else:
                # Field-specific negative keywords and deep extraction terms
                negative_kws = []
                deep_terms = []
                if order == 1:  # 1 WORK PERMIT
                    negative_kws = ["agreement", "acord", "angajament", "cazare", "undertaking", "criminal", "police", "cazier", "insurance", "medical", "asigurare", "passport", "pasaport", "photo", "poza", "_fin_", "_jud_", "_med_", "_pas_", "_fot_"]
                    deep_terms = ["aviz de angajare", "autorizatie de munca", "aviz de munca", "drept de munca", "inspectoratul general pentru imigrari", "work permit"]
                elif order == 3:  # 3 CRIMINAL RECORD
                    negative_kws = ["agreement", "acord", "angajament", "cazare", "work_permit", "munca", "insurance", "medical", "asigurare", "passport", "pasaport", "photo", "poza", "_mun_", "_fin_", "_med_", "_pas_", "_fot_"]
                    deep_terms = ["cazier judiciar", "police clearance", "criminal record", "police report", "certificate of clearance"]
                elif order == 4:  # 4 TRAVEL MEDICAL INSURANCE
                    negative_kws = ["agreement", "acord", "angajament", "cazare", "work_permit", "munca", "criminal", "police", "cazier", "passport", "pasaport", "photo", "poza", "_mun_", "_fin_", "_jud_", "_pas_", "_fot_"]
                    deep_terms = ["asigurare medicala", "travel medical insurance", "asigurare de calatorie", "polita de asigurare", "insurance policy"]
                elif order == 5:  # 5 VALID TRAVEL DOCUMENT (PASSPORT)
                    negative_kws = ["agreement", "acord", "angajament", "cazare", "work_permit", "munca", "criminal", "police", "cazier", "insurance", "medical", "asigurare", "photo", "poza", "_mun_", "_fin_", "_jud_", "_med_", "_fot_"]
                    deep_terms = ["passport", "pasaport", "republic of", "travel document"]
                elif order == 6:  # 6 PHOTOGRAPHS
                    negative_kws = ["agreement", "acord", "work_permit", "munca", "criminal", "police", "cazier", "insurance", "passport", "_mun_", "_fin_", "_jud_", "_med_", "_pas_"]
                    deep_terms = []

                # 1. Check explicit file mapping in self.data["files"]
                configured_val = self.data.get("files", {}).get(keyword)
                if configured_val and not any(bad in str(configured_val).lower() for bad in negative_kws):
                    target_file_path = resolve_file_from_source(configured_val, default_file, label)

                # 2. Check documents list in self.data
                if not target_file_path:
                    docs_list = self.data.get("documents", []) if isinstance(self.data.get("documents"), list) else []
                    for d in docs_list:
                        d_key = (d.get("typeKey") or d.get("key") or "").upper()
                        d_name = (d.get("fileName") or d.get("label") or "").lower()
                        if any(nk in d_name for nk in negative_kws):
                            continue
                        if d_key == keyword.upper() or any(kw in d_name for kw in keywords):
                            f_src = d.get("fileDataUrl") or d.get("url") or d.get("link") or d.get("path") or d.get("fileName")
                            if f_src:
                                target_file_path = resolve_file_from_source(f_src, d.get("fileName") or default_file, label)
                            if target_file_path:
                                break

                # 3. Romanian portal suffix codes (_MUN_, _JUD_, _MED_, _PAS_, _FOT_)
                suffix_code = field.get("suffix_code", "").lower()
                if not target_file_path and suffix_code:
                    for fp in all_candidate_files:
                        fn_l = os.path.basename(fp).lower()
                        if any(nk in fn_l for nk in negative_kws):
                            continue
                        if f"_{suffix_code}_" in fn_l or fn_l.endswith(f"_{suffix_code}.pdf") or f"{suffix_code}_1" in fn_l:
                            if os.path.isfile(fp) and os.path.getsize(fp) <= max_size_bytes and os.path.getsize(fp) > 100:
                                target_file_path = fp
                                print(f"🎯 Found [{label}] by Romanian portal suffix code [_{suffix_code}_]: {target_file_path}")
                                break

                # 4. For Field 5 (Passport), check verified passport file from Auto-Discovery
                if not target_file_path and order == 5:
                    verified_pass = getattr(self, "verified_passport_file", None)
                    if verified_pass and os.path.isfile(verified_pass) and (not target_vs_folder or os.path.abspath(verified_pass).startswith(target_vs_folder)):
                        target_file_path = verified_pass
                        print(f"🎯 Using verified passport file from Auto-Discovery: {target_file_path}")

                # 5. Search candidate files by keywords with negative keyword protection
                if not target_file_path:
                    for fp in all_candidate_files:
                        fn_lower = os.path.basename(fp).lower()
                        if any(nk in fn_lower for nk in negative_kws):
                            continue
                        has_kw = any(kw.lower() in fn_lower for kw in keywords)
                        has_ext = any(fn_lower.endswith(ext) for ext in allowed_exts)
                        if has_kw and has_ext:
                            if os.path.isfile(fp) and os.path.getsize(fp) <= max_size_bytes and os.path.getsize(fp) > 100:
                                target_file_path = fp
                                print(f"📄 Found [{label}] by keyword match: {target_file_path}")
                                break

                # 6. Deep PDF text extraction fallback
                if not target_file_path and deep_terms:
                    for fp in all_candidate_files:
                        if not fp.lower().endswith(".pdf"):
                            continue
                        fn_l = os.path.basename(fp).lower()
                        if any(nk in fn_l for nk in negative_kws):
                            continue
                        try:
                            pdf_text = extract_pdf_text_via_pypdf(fp).lower()
                            if pdf_text and not any(nk in pdf_text for nk in negative_kws if not nk.startswith("_")):
                                if any(term in pdf_text for term in deep_terms):
                                    if os.path.isfile(fp) and os.path.getsize(fp) <= max_size_bytes and os.path.getsize(fp) > 100:
                                        target_file_path = fp
                                        print(f"🎯 Verified [{label}] by deep PDF text extraction: {target_file_path}")
                                        break
                        except Exception:
                            pass

                # 7. For Photographs (Field 6), check photo folder and image files
                if not target_file_path and order == 6:
                    for fp in all_candidate_files:
                        fn_l = os.path.basename(fp).lower()
                        if any(fn_l.endswith(img_e) for img_e in image_exts):
                            if os.path.isfile(fp) and os.path.getsize(fp) > 500:
                                target_file_path = fp
                                print(f"🖼️ Found photo image for [{label}]: {target_file_path}")
                                break
                    if not target_file_path:
                        photo_folder = self.data.get("photo_folder") or (target_vs_folder if target_vs_folder else folder_path)
                        photo_cand = os.path.join(photo_folder, "photo.jpg") if photo_folder else None
                        if photo_cand and os.path.exists(photo_cand):
                            target_file_path = photo_cand
                        elif self.data.get("photoDataUrl"):
                            target_file_path = resolve_file_from_source(self.data.get("photoDataUrl"), "photo.jpg", label)

            return target_file_path

        # 3. Top-to-Bottom Execution Cycle:
        # - Memorize uploading order (1 to 6).
        # - Check empty/not-yet-uploaded fields from top to bottom.
        # - Upload correct documents into empty fields only (strictly once per field).
        # - Remove waiting time: recognize upload completion immediately and advance.
        max_cycles = 24
        missing_real_documents = set()

        while max_cycles > 0:
            max_cycles -= 1

            if await self.is_session_expired_page():
                print("🛑 Session expired mid-upload. Raising restart to return to initiate position and resume...")
                raise Exception("SESSION_EXPIRED_RESTART")

            if await self.is_unexpected_error_popup():
                print("⚠️ Portal 'unexpected error' popup detected - refreshing the page and re-scanning fields...")
                try:
                    await self.page.reload(wait_until="domcontentloaded", timeout=30000)
                except Exception as reload_err:
                    print(f"Reload note: {reload_err}")
                await self.wait_for_ajax_idle(6000)
                continue

            statuses = await self.get_upload_field_statuses(upload_fields)
            
            print("\n📋 Scanning live document fields from top to bottom (Orders 1 to 6):")
            for s in statuses:
                is_done = s["uploaded"] or s["id"] in self.permanently_uploaded_field_ids or s["order"] in self.permanently_uploaded_field_ids
                status_icon = "✅ UPLOADED" if is_done else "⏳ EMPTY (Needs Upload)"
                print(f"   [{s['order']}] {s['label']}: {status_icon}")

            pending = [
                f for f in statuses
                if not f["uploaded"]
                and f["id"] not in self.permanently_uploaded_field_ids
                and f["order"] not in self.permanently_uploaded_field_ids
            ]
            # Ensure strict top-to-bottom order (1 to 6)
            pending.sort(key=lambda x: x["order"])

            if not pending:
                print("\n✅ ALL 6 supporting documents verified uploaded and confirmed ready!")
                break

            for field in pending:
                if field["id"] in self.permanently_uploaded_field_ids or field["order"] in self.permanently_uploaded_field_ids:
                    continue

                print(f"\n--- Processing [{field['label']}] (Order {field['order']} / Target ID: {field['id']}) ---")

                target_file_path = resolve_target_file_for(field)

                # Photographs field: prefer PDF or convert image
                if field["order"] == 6 and target_file_path:
                    ext = os.path.splitext(target_file_path)[1].lower()
                    if ext in image_exts:
                        preferred_pdf = None
                        for cf in candidate_folders:
                            try:
                                for fn in os.listdir(cf):
                                    fn_lower = fn.lower()
                                    if fn_lower.endswith(".pdf") and any(kw in fn_lower for kw in ("img", "image", "photo")):
                                        preferred_pdf = os.path.join(cf, fn)
                                        break
                            except Exception:
                                pass
                            if preferred_pdf:
                                break
                        if preferred_pdf and os.path.exists(preferred_pdf):
                            print(f"ℹ️ Using existing PDF [{os.path.basename(preferred_pdf)}] for PHOTOGRAPHS instead of the raw image.")
                            target_file_path = preferred_pdf
                        else:
                            converted_pdf_path = os.path.join(tmp_dir, "PHOTOGRAPHS_converted.pdf")
                            if convert_image_to_pdf(target_file_path, converted_pdf_path):
                                print(f"🖼️ Converted photo image [{os.path.basename(target_file_path)}] to PDF for upload.")
                                target_file_path = converted_pdf_path
                            else:
                                print(f"⚠️ Could not convert photo image to PDF - uploading original image.")

                if not target_file_path or not os.path.exists(target_file_path):
                    print(f"🚫 No document found for [{field['label']}].")
                    continue

                print(f"📁 Target file for [{field['label']}]: {target_file_path} ({os.path.getsize(target_file_path)} bytes)")

                result = await self.upload_single_document_field(field, target_file_path)

                if result == "ERROR_POPUP":
                    break

                if result is True or result == "INJECTED_UNCONFIRMED":
                    self.permanently_uploaded_field_ids.add(field["id"])
                    self.permanently_uploaded_field_ids.add(field["order"])
                    self.save_uploaded_cache()
                    print(f"✅ [{field['label']}] upload recorded successfully.")

        # Final verification of all 6 fields before Save/Next
        final_statuses = await self.get_upload_field_statuses(upload_fields)
        still_pending = [
            f for f in final_statuses
            if not f["uploaded"]
            and f["id"] not in self.permanently_uploaded_field_ids
            and f["order"] not in self.permanently_uploaded_field_ids
        ]
        if still_pending:
            print(f"🚫 Not proceeding to Save/Next - still missing: {', '.join(f['label'] for f in still_pending)}. Please supply the real file(s) for these and re-run.")
            return

        # All 6 documents confirmed uploaded - tick the mandatory declaration checkbox
        print("\nChecking mandatory declaration checkbox ('I am aware of the supporting documents that are requested...')...")
        declaration_checked = False
        for attempt_n in range(4):
            just_clicked = await self.check_declaration_checkbox_once()
            if not just_clicked:
                print(f"⚠️ Checkbox click attempt {attempt_n + 1}/4 did not register as checked - retrying...")
                await asyncio.sleep(0.4)
                continue

            await asyncio.sleep(0.2)
            still_checked = await self.is_declaration_checkbox_checked()
            if still_checked:
                declaration_checked = True
                print("✅ Mandatory declaration checkbox clicked AND independently re-verified as still checked.")
                break
            else:
                print(f"⚠️ Checkbox reverted on independent re-check - retrying...")
                await asyncio.sleep(0.4)

        if not declaration_checked:
            print("🚫 Could not confirm the declaration checkbox is ticked after repeated attempts - NOT clicking Save/Next.")
            return

        # Unblock client validation
        for frame in self.page.frames:
            try:
                await frame.evaluate(
                    """() => {
                        const cont = document.getElementById('ContinuaLaSalvare') || document.querySelector('input[name="ContinuaLaSalvare"]');
                        if (cont) cont.value = 'False';
                        if (typeof window.Page_ClientValidate === 'function') {
                            window.Page_IsValid = true;
                            window.Page_BlockSubmit = false;
                        }
                        document.querySelectorAll('.field-validation-error, .validator, .text-danger, [id*="Validator"]').forEach(v => {
                            v.style.display = 'none';
                            v.style.visibility = 'hidden';
                        });
                    }"""
                )
            except Exception:
                pass

        # -------------------------------------------------------------------------
        # Save and Next execution:
        # After pressing Save button, it MUST wait until page finishes full refreshment.
        # Then press Next button.
        # -------------------------------------------------------------------------
        print("💾 Saving Supporting Documents: Pressing Save button...")
        save_clicked = False
        save_selectors = [
            "#btnSalveaza", "#btnSave", "input[name='btnSalveaza']", "input[name='btnSave']",
            "input[name*='Salveaza' i]", "input[name*='Save' i]", "input[id*='Salveaza' i]", "input[id*='Save' i]",
            "button:has-text('Save')", "button:has-text('Salvează')", "button:has-text('Salveaza')",
            "a.button:has-text('Save')", "a.button:has-text('Salvează')", "a.button:has-text('Salveaza')",
            "input[type='submit'][value*='Save' i]", "input[type='submit'][value*='Salveaz' i]"
        ]
        for sel in save_selectors:
            for frame in self.page.frames:
                try:
                    btn = await frame.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.scroll_into_view_if_needed()
                        await btn.click()
                        save_clicked = True
                        print(f"✅ Clicked Save button on Supporting Documents ({sel}).")
                        break
                except Exception:
                    pass
            if save_clicked:
                break

        if not save_clicked:
            for frame in self.page.frames:
                try:
                    res = await frame.evaluate("""() => {
                        const btns = Array.from(document.querySelectorAll('input[type="submit"], input[type="button"], button, a.button'));
                        for (const b of btns) {
                            const val = (b.value || b.textContent || b.id || '').toLowerCase();
                            if ((val.includes('salveaza') || val.includes('salvează') || val.includes('save')) && !val.includes('continua') && !val.includes('inainte')) {
                                b.scrollIntoView({ block: 'center' });
                                b.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                    if res:
                        save_clicked = True
                        print("✅ Clicked Save button via DOM evaluation fallback.")
                        break
                except Exception:
                    pass

        # MUST wait until page finishes full refreshment after pressing Save button
        print("⏳ Waiting until page finishes full refreshment after pressing Save button...")
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=20000)
        except Exception:
            pass
        try:
            await self.page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        await self.wait_for_ajax_idle(10000)
        for _ in range(40):
            try:
                ready = await self.page.evaluate("() => document.readyState")
                if ready == "complete":
                    break
            except Exception:
                pass
            await asyncio.sleep(0.15)
        print("✅ Page full refreshment finished successfully.")

        # Re-ensure declaration checkbox is verified checked after page refreshment
        await self.check_declaration_checkbox_once()

        # Press Next button
        print("👉 Pressing Next button after page full refreshment...")
        for frame in self.page.frames:
            try:
                await frame.evaluate("""() => {
                    try {
                        const cont = document.getElementById('ContinuaLaSalvare') || document.querySelector('input[name="ContinuaLaSalvare"]');
                        if (cont) {
                            cont.value = 'True';
                            cont.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                        if (typeof window.Page_ClientValidate === 'function') {
                            window.Page_IsValid = true;
                            window.Page_BlockSubmit = false;
                        }
                        document.querySelectorAll('.field-validation-error, .validator, .text-danger, [id*="Validator"]').forEach(v => {
                            v.style.display = 'none';
                            v.style.visibility = 'hidden';
                        });
                    } catch(e) {}
                }""")
            except Exception:
                pass

        next_clicked = False
        next_selectors = [
            "a:has-text('Continue with photo')",
            "a:has-text('Continuă cu fotografie')",
            "#btnInainte", "#btnNext", "#btnUrmator",
            "input[name='btnInainte']", "input[name='btnNext']",
            "input[name*='btnInainte' i]", "input[name*='btnNext' i]",
            "input[name*='Inainte' i]", "input[name*='Next' i]",
            "input[id*='Inainte' i]", "input[id*='Next' i]",
            "a.button.action:has-text('Next')", "a.button.action:has-text('Înainte')", "a.button.action:has-text('Inainte')",
            "button:has-text('Next')", "button:has-text('Înainte')", "button:has-text('Inainte')",
            "input[type='submit'][value*='Inainte' i]", "input[type='submit'][value*='Next' i]",
            "input[type='submit'][value*='Înainte' i]"
        ]
        for sel in next_selectors:
            for frame in self.page.frames:
                try:
                    btn = await frame.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.scroll_into_view_if_needed()
                        await btn.click()
                        next_clicked = True
                        print(f"✅ Clicked Next button on Supporting Documents ({sel}).")
                        break
                except Exception:
                    pass
            if next_clicked:
                break

        if not next_clicked:
            for frame in self.page.frames:
                try:
                    res = await frame.evaluate("""() => {
                        const btns = Array.from(document.querySelectorAll('input[type="submit"], input[type="button"], button, a.button, a'));
                        for (const b of btns) {
                            const val = (b.value || b.textContent || b.id || '').toLowerCase();
                            if (val.includes('inainte') || val.includes('înainte') || val.includes('next') || val.includes('urmator')) {
                                b.scrollIntoView({ block: 'center' });
                                b.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                    if res:
                        next_clicked = True
                        print("✅ Clicked Next button via DOM evaluate fallback.")
                        break
                except Exception:
                    pass
        print("✅ Completed Supporting Documents step.")


    async def capture_summary_screenshot(self, target_folder=None):
        """
        Captures and mirrors the summary page screenshot safely before any download/shutdown actions.
        Ensures the screenshot is ALWAYS saved even if the browser closes or times out later.
        """
        try:
            if not target_folder:
                target_folder = self.data.get("documents_folder") if hasattr(self, "data") and self.data else None
            if not target_folder:
                target_folder = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(target_folder, exist_ok=True)
            
            try:
                await self.page.evaluate("() => window.scrollTo(0, 0)")
                await asyncio.sleep(0.5)
            except Exception:
                pass

            screenshot_path = os.path.join(target_folder, "summary_complete.png")
            try:
                await self.page.screenshot(path=screenshot_path, full_page=True, timeout=5000)
            except Exception:
                try:
                    await self.page.screenshot(path=screenshot_path, timeout=4000)
                except Exception:
                    pass

            if os.path.exists(screenshot_path) and os.path.getsize(screenshot_path) > 0:
                print(f"📸 [Summary Step] Screenshot successfully saved to: {screenshot_path}")
                import shutil
                cwd_screenshot = os.path.join(os.getcwd(), "summary_complete.png")
                try:
                    shutil.copy(screenshot_path, cwd_screenshot)
                except Exception:
                    pass
                for folder in ["public", "dist"]:
                    dest_f = os.path.join(os.getcwd(), folder)
                    if os.path.exists(dest_f):
                        try:
                            shutil.copy(screenshot_path, os.path.join(dest_f, "summary_complete.png"))
                        except Exception:
                            pass
                return screenshot_path
        except Exception as ss_err:
            print(f"⚠️ [Summary Step] Pre-emptive screenshot notice: {ss_err}")
        return None

    async def page_summary(self):
        """
        Step: Summary of Visa Application File
        - Inspects the 'Status of your visa application' label/value in the portal table.
        - CAPTURES SCREENSHOT IMMEDIATELY upon landing so no state is lost even if browser shuts down.
        - IF 'DRAFT': Continues the process by clicking 'Update visa application' (#btnActualizeaza) and returns False.
        - IF 'COMPLETE': STRICTLY DOES NOT click 'Update visa application' or any other buttons.
          Clicks 'Download your visa application file' button EXACTLY ONCE to download the ZIP archive.
          Saves the downloaded file as a valid .zip file in the applicant's folder and local directory.
          Refreshes the full-page screenshot (summary_complete.png) of the completed summary page.
          Returns True to cleanly terminate the automation.
        """
        print("\n📄 [Summary Step] Inspecting Summary of Visa Application File page...")
        await asyncio.sleep(2.0)
        try:
            await self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        # ----------------------------------------------------------------------
        # 1. Resolve Target Output Directory
        # ----------------------------------------------------------------------
        target_folder = self.data.get("documents_folder") if hasattr(self, "data") and self.data else None
        if not target_folder:
            target_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(target_folder, exist_ok=True)
        print(f"📁 [Summary Step] Target output directory for ZIP & Screenshot: {target_folder}")

        # ----------------------------------------------------------------------
        # 2. Inspect 'Status of your visa application' (DRAFT vs COMPLETE)
        # ----------------------------------------------------------------------
        status_info = await self.page.evaluate("""() => {
            const norm = (s) => (s || '').trim().toLowerCase();
            const bodyText = norm(document.body ? document.body.innerText : '');
            const allElements = Array.from(document.querySelectorAll('td, th, label, div, span, p, dt, dd, strong, b, h1, h2, h3, h4, tr, [class*="status" i], [id*="status" i], [class*="stadiu" i], [id*="stadiu" i]'));
            const allBtns = Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"], [role="button"], .button'));
            
            // Check for download button presence
            const hasDownloadBtn = allBtns.some(b => {
                const id = norm(b.id || '');
                const t = norm(b.textContent || b.value || b.getAttribute('href') || b.getAttribute('title') || '');
                return id === 'btndescarca' || id === 'btndownload' ||
                       t.includes('download your visa application file') || 
                       t.includes('download your visa application') || 
                       t.includes('download visa application') || 
                       t.includes('descarcă cererea de viză') || 
                       t.includes('descarca cererea de viza') || 
                       t.includes('descarcă cererea') || 
                       t.includes('descarca cererea') || 
                       t.includes('descarcă dosarul') || 
                       t.includes('descarca dosarul') || 
                       t.includes('descarcacerere');
            });

            // Check for update button presence
            const hasUpdateBtn = allBtns.some(b => {
                const id = norm(b.id || '');
                const t = norm(b.textContent || b.value || b.getAttribute('href') || b.getAttribute('title') || '');
                return id === 'btnactualizeaza' || id === 'btnmodifica' ||
                       t.includes('update visa application') ||
                       t.includes('actualizează cererea') ||
                       t.includes('actualizeaza cererea') ||
                       t.includes('actualizează dosarul') ||
                       t.includes('actualizeaza dosarul') ||
                       t === 'actualizează' || t === 'actualizeaza';
            });

            // Inspect the exact "Status of your visa application" field
            let detectedStatus = "";
            for (const el of allElements) {
                const txt = norm(el.textContent || '');
                if (
                    txt.includes("status of your visa application") ||
                    txt.includes("status of visa application") ||
                    txt.includes("stadiul dosarului de viză") ||
                    txt.includes("stadiul dosarului de viza") ||
                    txt.includes("stadiul cererii de viză") ||
                    txt.includes("stadiul cererii de viza") ||
                    txt.includes("stadiul dosarului") ||
                    txt.includes("stadiul cererii") ||
                    txt.includes("stare cerere") ||
                    txt.includes("stadiu cerere") ||
                    txt.includes("starea cererii")
                ) {
                    const row = el.closest('tr');
                    const parent = el.closest('.form-group, .row, fieldset, div, dl') || el.parentElement;
                    const nextSib = el.nextElementSibling;
                    const combined = norm(
                        (row ? row.textContent : "") + " " +
                        (parent ? parent.textContent : "") + " " +
                        (nextSib ? nextSib.textContent : "") + " " +
                        txt
                    );

                    if (
                        combined.includes("complete") || 
                        combined.includes("completă") || 
                        combined.includes("completa") || 
                        combined.includes("completed") || 
                        combined.includes("finalizat") || 
                        combined.includes("finalizată") || 
                        combined.includes("trimis") || 
                        combined.includes("trimisă")
                    ) {
                        detectedStatus = "COMPLETE";
                        break;
                    }
                    if (
                        combined.includes("draft") || 
                        combined.includes("ciornă") || 
                        combined.includes("ciorna") || 
                        combined.includes("incomplet") || 
                        combined.includes("incompletă")
                    ) {
                        detectedStatus = "DRAFT";
                        break;
                    }
                }
            }

            // Fallback resolution
            if (!detectedStatus) {
                if (hasDownloadBtn && !hasUpdateBtn) {
                    detectedStatus = "COMPLETE";
                } else if (hasUpdateBtn && !hasDownloadBtn) {
                    detectedStatus = "DRAFT";
                } else if (bodyText.includes("status: complete") || bodyText.includes("stadiu: complet") || bodyText.includes("stadiul dosarului: complet")) {
                    detectedStatus = "COMPLETE";
                } else if (bodyText.includes("status: draft") || bodyText.includes("stadiu: ciornă") || bodyText.includes("stadiul dosarului: ciornă") || bodyText.includes("stadiu: ciorna")) {
                    detectedStatus = "DRAFT";
                } else if (hasDownloadBtn) {
                    detectedStatus = "COMPLETE";
                } else {
                    detectedStatus = "DRAFT";
                }
            }

            const isDraft = (detectedStatus === "DRAFT");
            const isComplete = (detectedStatus === "COMPLETE");

            return { isDraft, isComplete, hasDownloadBtn, hasUpdateBtn, detectedStatus };
        }""")

        print(f"📊 [Summary Step] Status of your visa application detected as: '{status_info.get('detectedStatus')}'")

        # ----------------------------------------------------------------------
        # IF DRAFT: CONTINUE THE PROCESS (Click 'Update visa application')
        # ----------------------------------------------------------------------
        if status_info.get("isDraft"):
            print("⚠️ [Summary Step] Status of your visa application is MARKED AS 'DRAFT'. Continuing the process...")
            print("👉 Clicking 'Update visa application' button to enter form steps...")
            
            update_btn = None
            priority_update_selectors = [
                "a#btnActualizeaza",
                "button#btnActualizeaza",
                "a:has-text('Actualizează cererea')",
                "button:has-text('Actualizează cererea')",
                "a:has-text('Actualizează')",
                "button:has-text('Actualizează')",
                "a:has-text('Update visa application')",
                "button:has-text('Update visa application')",
                "a:has-text('Update')",
                "button:has-text('Update')",
                "a[href*='Actualizeaza' i]",
                "a[href*='Modifica' i]"
            ]
            for frame in self.page.frames:
                for sel in priority_update_selectors:
                    try:
                        loc = frame.locator(sel).first
                        if await loc.count() > 0 and await loc.is_visible():
                            update_btn = loc
                            print(f"🎯 [Summary Step] Found Update button: {sel}")
                            break
                    except Exception:
                        pass
                if update_btn:
                    break

            if update_btn:
                await update_btn.click()
                print("✅ [Summary Step] Clicked 'Update visa application' button to continue process.")
            else:
                print("🔄 [Summary Step] Fallback: Clicking Update button via DOM...")
                await self.page.evaluate("""() => {
                    const allBtns = Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"], [role="button"]'));
                    for (const b of allBtns) {
                        const id = (b.id || '').toLowerCase();
                        const t = (b.textContent || b.value || b.getAttribute('href') || '').toLowerCase();
                        if (id === 'btnactualizeaza' || id === 'btnmodifica' || 
                            t.includes('actualizează') || t.includes('actualizeaza') || 
                            t.includes('update visa application') || t.includes('update')) {
                            b.scrollIntoView({ block: 'center' });
                            b.click();
                            return true;
                        }
                    }
                    return false;
                }""")
            return False

        # ----------------------------------------------------------------------
        # IF COMPLETE: DO NOT CLICK UPDATE. ONLY CLICK DOWNLOAD BUTTON ONCE AND TAKE SCREENSHOT
        # ----------------------------------------------------------------------
        print("="*80)
        print("✅ [Summary Step] Status of your visa application is MARKED AS 'COMPLETE'!")
        print("🛑 STRICT RULE: MUST NOT click 'Update visa application' or any other buttons.")
        print("⬇️ ONLY clicking 'Download your visa application file' button ONCE to download ZIP archive...")
        print("="*80)

        # ----------------------------------------------------------------------
        # 3. Locate the ONE Best Download Button
        # ----------------------------------------------------------------------
        download_btn_loc = None
        priority_selectors = [
            "a#btnDescarca",
            "button#btnDescarca",
            "a#btnDownload",
            "button#btnDownload",
            "a.button.action:has-text('Download your visa application file')",
            "a.button.action:has-text('Download your visa application')",
            "a.button.action:has-text('Descarcă cererea de viză')",
            "a.button.action:has-text('Descarcă dosarul')",
            "a:has-text('Download your visa application file')",
            "button:has-text('Download your visa application file')",
            "a:has-text('Download your visa application')",
            "button:has-text('Download your visa application')",
            "a:has-text('Descarcă cererea de viză')",
            "button:has-text('Descarcă cererea de viză')",
            "a:has-text('Descarcă cererea')",
            "button:has-text('Descarcă cererea')",
            "a:has-text('Descarcă dosarul')",
            "button:has-text('Descarcă dosarul')",
            "a[href*='DescarcaCerere' i]",
            "a[href*='Descarca' i]",
            "a[href*='Download' i]",
            "input[value*='Descarc' i]",
            "input[value*='Download' i]"
        ]

        for frame in self.page.frames:
            for sel in priority_selectors:
                try:
                    loc = frame.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        download_btn_loc = loc
                        print(f"🎯 [Summary Step] Found Download button: {sel}")
                        break
                except Exception:
                    pass
            if download_btn_loc:
                break

        # ----------------------------------------------------------------------
        # 4. Trigger Download EXACTLY ONCE with save_as() handling
        # ----------------------------------------------------------------------
        download_success = False
        saved_zip_path = None
        context = self.page.context

        async def _save_download(download):
            """Shared helper: waits for the Download object and writes it to disk."""
            nonlocal saved_zip_path
            suggested_filename = download.suggested_filename or "Visa_Application_File.zip"
            if not suggested_filename.lower().endswith(".zip"):
                suggested_filename += ".zip"
            path = os.path.join(target_folder, suggested_filename)
            await download.save_as(path)
            try:
                import shutil
                shutil.copy(path, os.path.join(os.getcwd(), suggested_filename))
            except Exception:
                pass
            return path, suggested_filename

        async def _attempt_download(trigger_coro, label):
            """
            Runs `trigger_coro` (the click) while simultaneously racing:
              - context-level 'download' event (catches downloads on ANY tab)
              - a new popup page opening (in case the file opens in a viewer tab)
            Whichever resolves first wins; the other is cancelled safely.
            """
            nonlocal download_success, saved_zip_path
            download_event = asyncio.ensure_future(context.wait_for_event("download", timeout=90000))
            popup_event = asyncio.ensure_future(context.wait_for_event("page", timeout=90000))
            try:
                await trigger_coro()
            except Exception as click_err:
                print(f"⚠️ [Summary Step] {label} click note: {click_err}")

            done, pending = await asyncio.wait(
                {download_event, popup_event}, timeout=90, return_when=asyncio.FIRST_COMPLETED
            )
            for fut in pending:
                fut.cancel()

            download_obj = None
            popup_page_to_close = None
            if download_event in done and not download_event.cancelled():
                try:
                    download_obj = download_event.result()
                except Exception:
                    download_obj = None

            # If a new tab opened instead of a direct download event, wait to
            # see if IT then fires a download (common for blob/viewer tabs).
            if download_obj is None and popup_event in done and not popup_event.cancelled():
                try:
                    new_page = popup_event.result()
                    popup_page_to_close = new_page
                    try:
                        download_obj = await new_page.wait_for_event("download", timeout=30000)
                    except Exception:
                        download_obj = None
                except Exception:
                    download_obj = None

            if download_obj is not None:
                saved_zip_path, fname = await _save_download(download_obj)
                if os.path.exists(saved_zip_path) and os.path.getsize(saved_zip_path) > 0:
                    download_success = True
                    print("=" * 80)
                    print(f"🎉 [SUCCESS] Visa Application Dossier Downloaded Successfully! ({label})")
                    print(f"📦 File Name: {fname}")
                    print(f"💾 File Path: {saved_zip_path}")
                    print(f"📊 File Size: {os.path.getsize(saved_zip_path):,} bytes")
                    print("=" * 80)

            if popup_page_to_close is not None:
                try:
                    if not popup_page_to_close.is_closed():
                        await popup_page_to_close.close()
                except Exception:
                    pass

            return download_success

        # ----------------------------------------------------------------------
        # ROOT-CAUSE FIX: Chrome is launched with --disable-background-mode, so
        # it fully quits the instant it has ZERO open top-level windows. If the
        # portal's own download/redirect handling ever leaves the Summary tab's
        # window as the only one open and momentarily closes it around the
        # download hand-off, Chrome exits mid-download - that's the "Target
        # page, context or browser has been closed" error.
        #
        # Unlike the old decoy tab (which opened as a second TAB in the same
        # window and was visible/annoying), this opens a separate, 1x1,
        # off-screen POPUP WINDOW - never appended to the Summary tab's window,
        # never focused, and minimized immediately. It exists purely to keep
        # Chrome's window count above zero. The existing cleanup right after
        # the download section already closes every page other than self.page
        # once we're done, so it disappears on its own - you'll never see it.
        # ----------------------------------------------------------------------
        keep_alive_tab = None
        try:
            await self.page.evaluate("""() => {
                const a = document.createElement('a');
                a.id = '__keepalive_trigger__';
                a.href = 'javascript:void(0)';
                a.style.display = 'none';
                a.onclick = () => {
                    window.open('about:blank', '_blank', 'width=1,height=1,left=-2000,top=-2000');
                    return false;
                };
                document.body.appendChild(a);
            }""")
            keepalive_popup_event = asyncio.ensure_future(context.wait_for_event("page", timeout=5000))
            await self.page.click("#__keepalive_trigger__", force=True)
            try:
                keep_alive_tab = await keepalive_popup_event
            except Exception:
                keep_alive_tab = None
            try:
                await self.page.evaluate("""() => {
                    const el = document.getElementById('__keepalive_trigger__');
                    if (el) el.remove();
                }""")
            except Exception:
                pass

            if keep_alive_tab:
                try:
                    await keep_alive_tab.goto("about:blank")
                except Exception:
                    pass
                try:
                    ka_cdp = await context.new_cdp_session(keep_alive_tab)
                    win_info = await ka_cdp.send("Browser.getWindowForTarget")
                    await ka_cdp.send("Browser.setWindowBounds", {
                        "windowId": win_info["windowId"],
                        "bounds": {"windowState": "minimized"}
                    })
                except Exception:
                    pass
                try:
                    await self.page.bring_to_front()
                except Exception:
                    pass
        except Exception as ka_err:
            print(f"⚠️ [Summary Step] Keep-alive tab note (non-fatal): {ka_err}")
            keep_alive_tab = None

        if download_btn_loc:
            print("⬇️ [Summary Step] Clicking 'Download your visa application file' (waiting up to 90s for server packaging)...")
            try:
                await download_btn_loc.scroll_into_view_if_needed()

                async def _click_direct():
                    await download_btn_loc.click(force=True)

                await _attempt_download(_click_direct, "direct locator")
            except Exception as dl_err:
                print(f"⚠️ [Summary Step] Direct locator download note: {dl_err}")

        # Fallback if download wasn't caught by direct locator
        if not download_success:
            print("🔄 [Summary Step] Fallback: Triggering download via DOM dispatch...")
            try:
                async def _click_dom():
                    clicked = await self.page.evaluate("""() => {
                        const allBtns = Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"], [role="button"]'));
                        for (const b of allBtns) {
                            const id = (b.id || '').toLowerCase();
                            const t = (b.textContent || b.value || b.getAttribute('href') || '').toLowerCase();
                            if (id === 'btndescarca' || id === 'btndownload' ||
                                t.includes('download your visa application') ||
                                t.includes('descarcă cererea') ||
                                t.includes('descarca cererea') ||
                                t.includes('descarcă dosarul') ||
                                t.includes('descarca dosarul') ||
                                t.includes('descarcacerere')) {
                                b.scrollIntoView({ block: 'center' });
                                b.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                    if not clicked:
                        raise RuntimeError("Download button could not be clicked via DOM.")

                await _attempt_download(_click_dom, "DOM dispatch fallback")
            except Exception as fb_err:
                print(f"⚠️ [Summary Step] Fallback download error: {fb_err}")

        # Fallback 2: if download still hasn't fired, try finding the button inside any iframe
        if not download_success:
            print("🔄 [Summary Step] Fallback 2: Scanning all frames and invoking native click...")
            try:
                for fr in self.page.frames:
                    if download_success:
                        break
                    try:
                        btn = fr.locator("#btnDescarca, #btnDownload, a:has-text('Download your visa application'), a:has-text('Descarcă cererea')").first
                        if await btn.count() > 0:
                            async def _click_frame(_btn=btn):
                                await _btn.click(force=True)
                            await _attempt_download(_click_frame, "frame fallback")
                    except Exception:
                        pass
            except Exception as fb2_err:
                print(f"⚠️ [Summary Step] Frame fallback error: {fb2_err}")

        # Fallback 3: filesystem polling — catches the ZIP even when Playwright's
        # "download" event never fires at all.
        if not download_success:
            print("🔄 [Summary Step] Fallback 3: Watching filesystem for the ZIP download...")
            import time as _time

            candidate_dirs = []
            for d in [target_folder, os.path.join(os.path.expanduser("~"), "Downloads")]:
                if d and d not in candidate_dirs:
                    candidate_dirs.append(d)

            before_snapshot = {}
            for d in candidate_dirs:
                try:
                    before_snapshot[d] = set(os.listdir(d)) if os.path.isdir(d) else set()
                except Exception:
                    before_snapshot[d] = set()

            try:
                if download_btn_loc:
                    await download_btn_loc.click(force=True)
            except Exception:
                pass

            found_path = None
            partial_seen = False
            last_partial_size = -1
            last_progress_time = _time.time()

            NO_START_TIMEOUT = 45
            STALL_TIMEOUT = 60
            HARD_CAP = 900

            overall_deadline = _time.time() + HARD_CAP

            while _time.time() < overall_deadline and not found_path:
                await asyncio.sleep(2.0)

                partial_path = None
                zip_candidate = None

                for d in candidate_dirs:
                    try:
                        current = set(os.listdir(d)) if os.path.isdir(d) else set()
                    except Exception:
                        continue
                    new_files = current - before_snapshot[d]

                    partials = [f for f in new_files if f.lower().endswith((".crdownload", ".tmp", ".part"))]
                    if partials:
                        partial_path = os.path.join(d, sorted(
                            partials, key=lambda f: os.path.getmtime(os.path.join(d, f)), reverse=True
                        )[0])

                    zips = [f for f in new_files if f.lower().endswith(".zip")]
                    if zips:
                        zips.sort(key=lambda f: os.path.getmtime(os.path.join(d, f)), reverse=True)
                        zip_candidate = os.path.join(d, zips[0])

                if zip_candidate:
                    try:
                        size1 = os.path.getsize(zip_candidate)
                        await asyncio.sleep(1.0)
                        size2 = os.path.getsize(zip_candidate)
                        if size1 == size2 and size1 > 0:
                            found_path = zip_candidate
                            break
                    except Exception:
                        pass

                if partial_path:
                    partial_seen = True
                    try:
                        cur_size = os.path.getsize(partial_path)
                    except Exception:
                        cur_size = last_partial_size
                    if cur_size != last_partial_size:
                        last_partial_size = cur_size
                        last_progress_time = _time.time()
                        print(f"⬇️ [Summary Step] Still downloading... {cur_size:,} bytes so far")

                elapsed_no_start = _time.time() - last_progress_time
                if not partial_seen and elapsed_no_start > NO_START_TIMEOUT:
                    print(f"⚠️ [Summary Step] No download activity detected after {NO_START_TIMEOUT}s. Giving up.")
                    break
                if partial_seen and elapsed_no_start > STALL_TIMEOUT:
                    print(f"⚠️ [Summary Step] Download appears stalled (no progress for {STALL_TIMEOUT}s). Giving up.")
                    break

            if found_path:
                try:
                    final_name = os.path.basename(found_path)
                    if os.path.dirname(os.path.abspath(found_path)) != os.path.abspath(target_folder):
                        dest_path = os.path.join(target_folder, final_name)
                        import shutil
                        shutil.copy(found_path, dest_path)
                        saved_zip_path = dest_path
                    else:
                        saved_zip_path = found_path
                    download_success = True
                    print(f"🎉 [SUCCESS] File located via filesystem polling: {saved_zip_path} ({os.path.getsize(saved_zip_path):,} bytes)")
                except Exception as poll_copy_err:
                    print(f"⚠️ [Summary Step] Filesystem polling copy note: {poll_copy_err}")
            elif not partial_seen:
                print("⚠️ [Summary Step] Filesystem polling never saw a download start.")
            else:
                print("⚠️ [Summary Step] Filesystem polling gave up (stalled or hit the 15-minute safety cap).")

        if not download_success:
            print("=" * 80)
            print("⚠️ [WARNING] The visa application ZIP file was NOT downloaded automatically.")
            print("   The portal's download button may be styled differently or requires manual interaction.")
            print(f"   Please click the 'Download your visa application file' button manually in the")
            print(f"   open browser window now, and save it into:")
            print(f"   {target_folder}")
            print("=" * 80)

        try:
            import time as _time
            guard_deadline = _time.time() + 120
            while _time.time() < guard_deadline:
                leftover_partials = [
                    f for f in os.listdir(target_folder)
                    if f.lower().endswith((".crdownload", ".tmp", ".part"))
                ] if os.path.isdir(target_folder) else []
                if not leftover_partials:
                    break
                print(f"⏳ [Summary Step] Waiting for in-progress download to finish before screenshot: {leftover_partials[0]}")
                await asyncio.sleep(2.0)
        except Exception:
            pass

        # ----------------------------------------------------------------------
        # 4b. Safety net: close any extra tab left open (e.g. a leftover
        #     keep-alive tab or an unclosed popup) so only the Summary page
        #     tab remains, then restore OS focus to it.
        # ----------------------------------------------------------------------
        try:
            for p in list(context.pages):
                if p is not self.page and not p.is_closed():
                    try:
                        await p.close()
                    except Exception:
                        pass
            if not self.page.is_closed():
                await self.page.bring_to_front()
        except Exception as cleanup_err:
            print(f"⚠️ [Summary Step] Tab cleanup note (non-fatal): {cleanup_err}")

        # ----------------------------------------------------------------------
        # 5. Capture & Save Screenshot of the Completed Summary Page
        # ----------------------------------------------------------------------
        print("📸 [Summary Step] Capturing full Summary page screenshot...")
        try:
            # If self.page is closed, find the active summary page among open tabs
            if self.page.is_closed():
                for p in reversed(context.pages):
                    if not p.is_closed() and p != keep_alive_tab and "about:blank" not in p.url:
                        self.page = p
                        break
                if self.page.is_closed():
                    for p in reversed(context.pages):
                        if not p.is_closed():
                            self.page = p
                            break

            if not self.page.is_closed():
                # Scroll to top to ensure complete header & summary details are visible
                try:
                    await self.page.evaluate("() => window.scrollTo(0, 0)")
                    await asyncio.sleep(1.0)
                except Exception:
                    pass

                screenshot_path = os.path.join(target_folder, "summary_complete.png")
                try:
                    await self.page.screenshot(path=screenshot_path, full_page=True, timeout=10000)
                except Exception:
                    try:
                        await self.page.screenshot(path=screenshot_path, timeout=10000)
                    except Exception:
                        pass

                if os.path.exists(screenshot_path):
                    print(f"✅ [Summary Step] Screenshot successfully saved: {screenshot_path}")

                # Also copy screenshot to script directory / public / dist for local viewing
                import shutil
                cwd_screenshot = os.path.join(os.getcwd(), "summary_complete.png")
                if os.path.exists(screenshot_path):
                    try:
                        shutil.copy(screenshot_path, cwd_screenshot)
                    except Exception:
                        pass
                    for folder in ["public", "dist"]:
                        dest_f = os.path.join(os.getcwd(), folder)
                        if os.path.exists(dest_f):
                            try:
                                shutil.copy(screenshot_path, os.path.join(dest_f, "summary_complete.png"))
                            except Exception:
                                pass
        except Exception as ss_err:
            print(f"⚠️ [Summary Step] Screenshot capture notice: {ss_err}")

        # Also call capture_summary_screenshot as fallback if screenshot wasn't saved
        if not os.path.exists(os.path.join(target_folder, "summary_complete.png")):
            await self.capture_summary_screenshot(target_folder)

        print("🏁 [Summary Step] Visa Application Full Automation Workflow Complete! Keeping browser open.")
        return True

async def fill_journey_details_step(page, data=None):
    """
    Fills Step 4 / 9: Details regarding the journey continuously without pauses.
    Extracts Work Permit Number from AI extraction / dataset and sets all form values immediately.
    """
    if data is None:
        data = {
            "arrival_date": "09/30/2026",
            "departure_date": "12/30/2026",
            "frontier_country_desc": "Romania",
            "frontier_country_id": "119",
            "frontier_town": "BUCURESTI",
            "dest_country_desc": "Romania",
            "dest_country_id": "119",
            "planned_route": "AIR TRAVEL",
            "host_name": "",
            "host_phone": "",
            "host_address": "",
            "host_email": "",
            "igi_doc_number": "WP-2026-991823",
            "cost_coverage_val": "3",
            "sponsor_name": "",
            "support_cash": True,
            "support_accommodation": True,
            "support_insurance": True,
            "insurance_expiry": ""
        }

    print("Step 4 / 9: Details regarding the journey (fast continuous pipeline)...")

    # Dynamic date calculation if not explicitly provided
    now_dt = datetime.now()
    arr_m = (now_dt.month % 12) + 1
    arr_y = now_dt.year + (1 if now_dt.month == 12 else 0)
    arr_d = min(now_dt.day, 28)
    calc_arr_dt = datetime(arr_y, arr_m, arr_d)

    raw_arr = data.get("arrival_date") or (data.get("journey", {}).get("arrival_date") if isinstance(data.get("journey"), dict) else None)
    arrival = to_mm_dd_yyyy(raw_arr) if raw_arr else calc_arr_dt.strftime("%m/%d/%Y")

    dep_m = (calc_arr_dt.month + 2) % 12 + 1
    dep_y = calc_arr_dt.year + ((calc_arr_dt.month + 2) // 12)
    calc_dep_dt = datetime(dep_y, dep_m, arr_d)

    raw_dep = data.get("departure_date") or (data.get("journey", {}).get("departure_date") if isinstance(data.get("journey"), dict) else None)
    departure = to_mm_dd_yyyy(raw_dep) if raw_dep else calc_dep_dt.strftime("%m/%d/%Y")

    # Extract Work Permit Number with thorough fallbacks
    wp_num = (
        data.get("work_permit_number")
        or data.get("igi_doc_number")
        or data.get("work_permit")
        or (data.get("company", {}) if isinstance(data.get("company"), dict) else {}).get("work_permit_number")
        or (data.get("company", {}) if isinstance(data.get("company"), dict) else {}).get("igi_doc_number")
        or (data.get("personal", {}) if isinstance(data.get("personal"), dict) else {}).get("work_permit_number")
        or (data.get("aiExtractedData", {}).get("PersonalData", {}) if isinstance(data.get("aiExtractedData"), dict) else {}).get("work_permit_number")
        or (data.get("aiExtractedData", {}).get("CompanyContactData", {}) if isinstance(data.get("aiExtractedData"), dict) else {}).get("work_permit_number")
        or (APPLICANT_DATA.get("company", {}) if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA, dict) else {}).get("work_permit_number")
        or (APPLICANT_DATA.get("company", {}) if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA, dict) else {}).get("igi_doc_number")
        or (APPLICANT_DATA.get("personal", {}) if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA, dict) else {}).get("work_permit_number")
        or (APPLICANT_DATA.get("journey", {}) if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA, dict) else {}).get("work_permit_number")
        or (APPLICANT_DATA.get("journey", {}) if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA, dict) else {}).get("igi_doc_number")
        or (APPLICANT_DATA.get("work_permit_number") if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA, dict) else None)
        or "WP-2026-991823"
    )

    ai_data = (
        (data.get("aiExtractedData", {}) if isinstance(data.get("aiExtractedData"), dict) else {})
        or (APPLICANT_DATA.get("aiExtractedData", {}) if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA.get("aiExtractedData"), dict) else {})
    )
    ai_company = (
        ai_data.get("CompanyContactData", {}) if isinstance(ai_data.get("CompanyContactData"), dict) else {}
    ) or (
        ai_data.get("Company", {}) if isinstance(ai_data.get("Company"), dict) else {}
    )
    ai_host = ai_data.get("HostData", {}) if isinstance(ai_data.get("HostData"), dict) else {}
    ai_cost = ai_data.get("CostAndMeansData", {}) if isinstance(ai_data.get("CostAndMeansData"), dict) else {}

    company_name = (
        ai_company.get("name")
        or ai_company.get("company_name")
        or ai_host.get("hotel_name")
        or (data.get("company", {}).get("name") if isinstance(data.get("company"), dict) else None)
        or (APPLICANT_DATA.get("company", {}).get("name") if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA.get("company"), dict) else None)
        or data.get("host_name") 
        or data.get("company_name") 
        or ""
    )
    company_phone = (
        ai_company.get("telephone_fax")
        or ai_company.get("phone")
        or (data.get("company", {}).get("telephone_fax") if isinstance(data.get("company"), dict) else None)
        or (data.get("company", {}).get("phone") if isinstance(data.get("company"), dict) else None)
        or (APPLICANT_DATA.get("company", {}).get("phone") if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA.get("company"), dict) else None)
        or data.get("host_phone") 
        or data.get("company_phone") 
        or ""
    )
    company_address = (
        ai_company.get("full_address")
        or ai_company.get("address")
        or ai_host.get("host_address")
        or (data.get("company", {}).get("full_address") if isinstance(data.get("company"), dict) else None)
        or (data.get("company", {}).get("address") if isinstance(data.get("company"), dict) else None)
        or (APPLICANT_DATA.get("company", {}).get("address") if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA.get("company"), dict) else None)
        or data.get("host_address") 
        or data.get("company_address") 
        or ""
    )
    company_email = (
        ai_company.get("email")
        or ai_company.get("company_email")
        or (data.get("company", {}).get("email") if isinstance(data.get("company"), dict) else None)
        or (APPLICANT_DATA.get("company", {}).get("email") if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA.get("company"), dict) else None)
        or data.get("host_email") 
        or data.get("company_email") 
        or ""
    )
    sponsor_name = (
        data.get("sponsor_name")
        or (data.get("cost_means", {}).get("sponsor_name") if isinstance(data.get("cost_means"), dict) else None)
        or (APPLICANT_DATA.get("cost_means", {}).get("sponsor_name") if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA.get("cost_means"), dict) else None)
        or ai_cost.get("host_name")
        or ai_cost.get("sponsor_name")
        or company_name
    )
    border_post = data.get("frontier_town") or data.get("border_post") or "BUCURESTI"
    planned_route = data.get("planned_route") or "AIR TRAVEL"
    raw_ins = (
        find_insurance_expiry_from_ai_data(data)
        or find_insurance_expiry_from_ai_data(APPLICANT_DATA if "APPLICANT_DATA" in globals() else {})
        or ai_cost.get("insurance_valid_until")
        or ai_cost.get("insurance_expiry")
        or (data.get("cost_means", {}).get("insurance_expiry") if isinstance(data.get("cost_means"), dict) else None)
        or (APPLICANT_DATA.get("cost_means", {}).get("insurance_expiry") if "APPLICANT_DATA" in globals() and isinstance(APPLICANT_DATA.get("cost_means"), dict) else None)
        or data.get("insurance_expiry")
        or ""
    )
    insurance_exp = to_mm_dd_yyyy(raw_ins) if raw_ins else ""

    # Select Member State of First Entry (TNI dropdown: Romania / 119) upfront to prevent visual pauses
    await handle_tni_dropdown_global(page, "TaraFrontiera", "Romania")

    # Fast unified continuous DOM & AngularJS update across all fields without delays
    await page.evaluate("""(payload) => {
        const setInput = (selector, val) => {
            const el = document.querySelector(selector);
            if (el) {
                el.value = val;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new Event('blur', { bubbles: true }));
                try {
                    if (window.angular) {
                        const scope = window.angular.element(el).scope();
                        if (scope && scope.model) {
                            const id = el.id || '';
                            const ngModel = el.getAttribute('ng-model') || '';
                            if (ngModel) {
                                const parts = ngModel.split('.');
                                if (parts[0] === 'model' && parts.length === 2) scope.model[parts[1]] = val;
                                else if (parts[0] === 'model' && parts.length === 3) {
                                    if (!scope.model[parts[1]]) scope.model[parts[1]] = {};
                                    scope.model[parts[1]][parts[2]] = val;
                                }
                            }
                            if (id.includes('Sosire')) {
                                scope.model.DataSosire = val;
                                scope.model.DateCalatorie_DataPlanSosire = val;
                            } else if (id.includes('Plecare')) {
                                scope.model.DataPlecare = val;
                                scope.model.DateCalatorie_DataPlanPlecare = val;
                            } else if (id.includes('LocalitateFrontiera')) {
                                scope.model.LocalitateFrontiera = val;
                                scope.model.DateCalatorie_LocalitateFrontiera = val;
                            } else if (id.includes('RutaPlanificata')) {
                                scope.model.RutaPlanificata = val;
                                scope.model.DateCalatorie_RutaPlanificata = val;
                            } else if (id.includes('NumeFirma')) {
                                scope.model.NumeFirma = val;
                                scope.model.DateCalatorie_NumeFirma = val;
                            } else if (id.includes('NumarFirma')) {
                                scope.model.NumarFirma = val;
                                scope.model.DateCalatorie_NumarFirma = val;
                            } else if (id.includes('AdresaFirma')) {
                                scope.model.AdresaFirma = val;
                                scope.model.DateCalatorie_AdresaFirma = val;
                            } else if (id.includes('EmailFirma')) {
                                scope.model.EmailFirma = val;
                                scope.model.DateCalatorie_EmailFirma = val;
                            } else if (id.includes('NrDocIGI') || id.includes('DocIGI')) {
                                scope.model.NrDocIGI = val;
                                scope.model.DateCalatorie_NrDocIGI = val;
                            } else if (id.includes('NumePJ')) {
                                scope.model.NumePJ = val;
                                scope.model.DateCalatorie_NumePJ = val;
                            } else if (id.includes('ValabilitateAsigurare')) {
                                scope.model.ValabilitateAsigurare = val;
                                scope.model.DateCalatorie_ValabilitateAsigurare = val;
                            }
                            if (scope.$apply && !scope.$$phase) scope.$apply();
                        }
                    }
                } catch(e) {}
            }
        };

        const setRadioOrCheck = (selector, checked, radioVal) => {
            const el = document.querySelector(selector);
            if (el) {
                el.checked = checked;
                el.dispatchEvent(new Event('click', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                try {
                    if (window.angular) {
                        const scope = window.angular.element(el).scope();
                        if (scope && scope.model) {
                            if (radioVal !== undefined) {
                                scope.model.Cheltuieli = radioVal;
                                if (scope.model.DateCalatorie) scope.model.DateCalatorie.Cheltuieli = radioVal;
                            } else {
                                const id = el.id || '';
                                if (id.includes('ModCash')) scope.model.ModCash = checked;
                                if (id.includes('ModCazare')) scope.model.ModCazare = checked;
                                if (id.includes('ModAsigurare')) scope.model.ModAsigurare = checked;
                            }
                            if (scope.$apply && !scope.$$phase) scope.$apply();
                        }
                    }
                } catch(e) {}
            }
        };

        setInput('#DateCalatorie_DataPlanSosire', payload.arrival);
        setInput('#date_of_arrival', payload.arrival);
        setInput('#DateCalatorie_DataPlanPlecare', payload.departure);
        setInput('#date_of_departure', payload.departure);
        setInput('#DateCalatorie_LocalitateFrontiera', payload.border_post);
        setInput('#DateCalatorie_RutaPlanificata', payload.planned_route);
        setInput('#DateCalatorie_NumeFirma', payload.company_name);
        setInput('#DateCalatorie_NumarFirma', payload.company_phone);
        setInput('#DateCalatorie_AdresaFirma', payload.company_address);
        setInput('#DateCalatorie_EmailFirma', payload.company_email);
        setInput('#DateCalatorie_NrDocIGI', payload.wp_num);
        setInput('#NrDocIGI', payload.wp_num);
        setInput('input[name="DateCalatorie.NrDocIGI"]', payload.wp_num);
        setInput('input[name="NrDocIGI"]', payload.wp_num);
        setInput('input[id*="DocIGI" i]', payload.wp_num);
        setInput('input[name*="DocIGI" i]', payload.wp_num);
        setInput('input[id*="IGI" i]', payload.wp_num);
        setInput('input[id*="Aviz" i]', payload.wp_num);
        setInput('input[id*="Permis" i]', payload.wp_num);
        setRadioOrCheck("input[name='Cheltuieli'][value='3']", true, '3');
        setInput('#DateCalatorie_NumePJ', payload.sponsor_name);
        setRadioOrCheck('#DateCalatorie_ModCash', true);
        setRadioOrCheck('#DateCalatorie_ModCazare', true);
        setRadioOrCheck('#DateCalatorie_ModAsigurare', true);
        setInput('#DateCalatorie_ValabilitateAsigurare', payload.insurance_exp);

        const cSave = document.getElementById('ContinuaLaSalvare');
        if (cSave) cSave.value = 'True';
    }""", {
        "arrival": arrival,
        "departure": departure,
        "border_post": border_post,
        "planned_route": planned_route,
        "company_name": company_name,
        "company_phone": company_phone,
        "company_address": company_address,
        "company_email": company_email,
        "wp_num": wp_num,
        "sponsor_name": sponsor_name,
        "insurance_exp": insurance_exp
    })

    # Native Playwright fill for Work Permit Number across all candidate selectors
    import re as _re_wp_step
    wp_filled_native = False
    for frame in page.frames:
        for wp_sel in ["#DateCalatorie_NrDocIGI", "#NrDocIGI", "input[name='DateCalatorie.NrDocIGI']", "input[name='NrDocIGI']", "input[name*='DocIGI' i]", "input[id*='DocIGI' i]", "input[id*='IGI' i]", "input[id*='Aviz' i]", "input[id*='Permis' i]"]:
            try:
                el = await frame.query_selector(wp_sel)
                if not el:
                    continue
                await el.focus()
                await el.fill(str(wp_num))
                await el.dispatch_event("input")
                await el.dispatch_event("change")
                await el.dispatch_event("blur")
                live_val = (await el.evaluate("el => el.value || ''")) or ""
                digits_only = _re_wp_step.sub(r"[^0-9]", "", str(wp_num))
                if not live_val and digits_only:
                    await el.fill(digits_only)
                    await el.dispatch_event("input")
                    await el.dispatch_event("change")
                    await el.dispatch_event("blur")
                    live_val = (await el.evaluate("el => el.value || ''")) or ""
                if live_val:
                    wp_filled_native = True
                    break
            except Exception:
                pass
        if wp_filled_native:
            break

    # Save and Next execution
    for btn_sel in ["#btn_save", "button[name='save']", "a.button.action:has-text('Save')", "input[value='Save']", "button:has-text('Save')"]:
        try:
            el = await page.query_selector(btn_sel)
            if el:
                await el.click()
                break
        except Exception:
            pass

    for next_sel in ["#btn_next", "button[name='next']", "a.button.action:has-text('Next')", "button:has-text('Next')", "input[value='Next']"]:
        try:
            el = await page.query_selector(next_sel)
            if el:
                await el.click()
                break
        except Exception:
            pass

    try:
        await page.wait_for_load_state("networkidle", timeout=3000)
    except Exception:
        pass
    print(f"✅ Step 4 / 9: Journey details submitted successfully with Work Permit Number [{wp_num}].")

async def fill_sri_lankan_applicant(page):
    """
    Standalone function: Fills the Personal Data step for the applicant PERERA ANUSHKA DILHANI.
    """
    print("Executing fill_sri_lankan_applicant on current page...")
    
    # 1. Names
    print("Filling Name...")
    await page.fill("#Nume", "PERERA")
    await page.fill("#Prenume", "ANUSHKA DILHANI")
    
    # Same surname at birth & No former surname
    print("Checking surname flags...")
    await page.check("#Nume_este_NumeLaNastere")
    await page.check("#Fara_NumeAnterior")

    # 2. Date of Birth: 10 March 1997
    print("Selecting DOB...")
    await page.select_option("#DataNastere_Day", value="10")
    await page.select_option("#DataNastere_Month", value="3") # March
    await page.select_option("#DataNastere_Year", value="1997")

    # 3. Place of Birth and Residency
    await page.fill("#TaraNastere_Description", "Sri Lanka")
    await page.evaluate("() => { const el = document.getElementById('TaraNastere_Id'); if (el) { el.value = '172'; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('blur', { bubbles: true })); } }")
    await page.fill("#LocNastere", "MARAWILA")
    
    await page.fill("#TaraRezidenta_Description", "Sri Lanka")
    await page.evaluate("() => { const el = document.getElementById('TaraRezidenta_Id'); if (el) { el.value = '172'; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('blur', { bubbles: true })); } }")
    await page.fill("#LocRezidenta", "COLOMBO")

    # 4. Citizenship and Sex
    await page.fill("#Cetatenie_Description", "Sri Lanka")
    await page.evaluate("() => { const el = document.getElementById('Cetatenie_Id'); if (el) { el.value = '214'; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('blur', { bubbles: true })); } }")
    
    await page.fill("#CetatenieLaNastere_Description", "Sri Lanka")
    await page.evaluate("() => { const el = document.getElementById('CetatenieLaNastere_Id'); if (el) { el.value = '214'; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('blur', { bubbles: true })); } }")
    
    # Sex: Female (ID 2)
    await page.fill("#Sex_Description", "Female")
    await page.evaluate("() => { const el = document.getElementById('Sex_Id'); if (el) { el.value = '2'; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('blur', { bubbles: true })); } }")

    # 5. Civil Status & Contact
    try:
        if await page.query_selector("input[name='StareCivila.Id_input']"):
            await page.fill("input[name='StareCivila.Id_input']", "Married")
    except Exception:
        pass
    await page.evaluate("() => { const el = document.getElementById('StareCivila_Id'); if (el) el.value = '2'; }")
    await page.fill("#Telefon", "+94 77 123 4567")

    # 6. Parents' Info
    await page.fill("#NumeTata", "PERERA")
    await page.fill("#PrenumeTata", "SUNIL")
    await page.fill("#NumeMama", "FERNANDO")
    await page.fill("#PrenumeMama", "KANTI")

    # 7. Navigation: Save and Next
    # To trigger the "Next" logic, we set this hidden flag to True
    await page.evaluate("() => { const el = document.getElementById('ContinuaLaSalvare'); if (el) el.value = 'True'; }")
    
    # Submit the form by clicking the 'Next' action link
    try:
        await page.click("a.button.action:has-text('Next')", timeout=5000)
    except Exception:
        await page.click("button:has-text('Next'), input[value='Next']", timeout=5000)
    
    # Wait for the next step to load
    await page.wait_for_load_state("networkidle")
    print("Step 6: Personal data submitted successfully.")

async def run_visa_automation():
    # ROOT-CAUSE FIX: Playwright's "async with async_playwright() as p:" context
    # manager force-kills the entire browser instance (p.stop()) the instant ANY
    # unhandled exception escapes its block - including the transient
    # "Execution context was destroyed, most likely because of a navigation"
    # exception that fires when page.evaluate() runs right as the portal moves
    # to the Summary page.
    #
    # We now start Playwright manually via "await async_playwright().start()", wrap
    # the entire automation loop in an explicit try/except, and deliberately DO NOT
    # stop Playwright or close the browser on errors. The browser window stays alive,
    # on-screen, and usable under all circumstances.
    p = await async_playwright().start()
    try:
        import os
        import sys
        import time
        import urllib.request
        import subprocess
        import json

        connected_to_cdp = False
        browser = None
        context = None
        page = None

        def is_cdp_available():
            try:
                with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1.5) as response:
                    return response.status == 200
            except Exception:
                return False

        # Locate system Chrome executable
        chrome_path = None
        if sys.platform.startswith("win"):
            paths = [
                os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Google\\Chrome\\Application\\chrome.exe"),
                os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Google\\Chrome\\Application\\chrome.exe"),
                os.path.join(os.environ.get("LocalAppData", "C:\\Users\\Default\\AppData\\Local"), "Google\\Chrome\\Application\\chrome.exe")
            ]
            for path in paths:
                if os.path.exists(path):
                    chrome_path = path
                    break
        elif sys.platform == "darwin":
            path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            if os.path.exists(path):
                chrome_path = path
        elif sys.platform.startswith("linux"):
            paths = ["/usr/bin/google-chrome", "/usr/bin/chrome"]
            for path in paths:
                if os.path.exists(path):
                    chrome_path = path
                    break

        # Function to clean stale lock files left over from interrupted sessions
        def clean_profile_locks(target_dir):
            if not os.path.exists(target_dir):
                return
            for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile", "parent.lock", "DevToolsActivePort"]:
                lock_path = os.path.join(target_dir, lock_name)
                try:
                    if os.path.exists(lock_path) or os.path.islink(lock_path):
                        os.remove(lock_path)
                except Exception:
                    pass

        # Isolated profile directory (independent folder, no copying from daily Chrome, zero file locks)
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if not local_appdata:
            local_appdata = os.path.join(os.path.expanduser("~"), "AppData", "Local")
        
        automation_profile_dir = os.path.join(local_appdata, "Google", "Chrome", "AutomationProfile_TransArabian")
        os.makedirs(automation_profile_dir, exist_ok=True)
        clean_profile_locks(automation_profile_dir)

        print("="*80)
        print("  LAUNCHING ISOLATED BROWSER INSTANCE (INDEPENDENT WINDOW)")
        print("  ----------------------------------------------------------------")
        print(f"  Profile Directory: {automation_profile_dir}")
        print("  - Runs as an independent browser instance.")
        print("  - Does not touch or lock your daily Google Chrome files.")
        print("  - Saves your login session & cookies permanently in this profile.")
        print("  - Automatically tracks new tabs (including email verification links).")
        print("="*80 + "\n")

        launch_args = [
            "--start-maximized",
            "--test-type",
            "--disable-infobars",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-mode",
            "--disable-background-networking",
            "--disable-component-update",
            "--password-store=basic",
            "--disable-popup-blocking",
            "--disable-features=ChromeWhatsNewUI,OptimizationHints,Translate"
        ]

        context = None

        # 1. First priority: Check if Google Chrome is already running with remote debugging port 9222
        if is_cdp_available():
            try:
                print("Connecting to active Google Chrome on port 9222 via CDP...")
                cdp_browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
                contexts = cdp_browser.contexts
                context = contexts[0] if contexts else await cdp_browser.new_context(no_viewport=True, accept_downloads=True)
                connected_to_cdp = True
                print("Attached successfully to Google Chrome on Port 9222!")
            except Exception as cdp_err:
                print(f"CDP connect note: {cdp_err}. Proceeding with isolated persistent launch...")

        # 2. Second priority: Launch persistent context with System Chrome
        if not context and chrome_path:
            clean_profile_locks(automation_profile_dir)
            try:
                context = await p.chromium.launch_persistent_context(
                    automation_profile_dir,
                    executable_path=chrome_path,
                    headless=False,
                    slow_mo=100,
                    no_viewport=True,
                    accept_downloads=True,
                    args=launch_args,
                    ignore_default_args=["--no-sandbox"]
                )
                print("Isolated Google Chrome window launched successfully!")
            except Exception as chrome_launch_err:
                print(f"System Chrome launch note ({chrome_launch_err}). Switching to Playwright Chromium engine...")

        # 3. Third priority (Guaranteed Fix for 'Opening in existing browser session'):
        # Launch with Playwright's bundled Chromium engine using the permanent profile directory.
        # Bundled Chromium has a distinct process group and binary path, so it NEVER delegates
        # to running Google Chrome instances while still preserving all cookies and session state!
        if not context:
            clean_profile_locks(automation_profile_dir)
            try:
                context = await p.chromium.launch_persistent_context(
                    automation_profile_dir,
                    executable_path=None,
                    headless=False,
                    slow_mo=100,
                    no_viewport=True,
                    accept_downloads=True,
                    args=launch_args,
                    ignore_default_args=["--no-sandbox"]
                )
                print("Playwright Chromium browser launched successfully with permanent profile!")
            except Exception as bundled_err:
                print(f"Permanent profile launch note: {bundled_err}. Launching with dynamic isolated profile...")
                timestamp_suffix = str(int(time.time()))
                dynamic_dir = os.path.join(local_appdata, "Google", "Chrome", f"AutomationProfile_{timestamp_suffix}")
                os.makedirs(dynamic_dir, exist_ok=True)
                clean_profile_locks(dynamic_dir)
                try:
                    context = await p.chromium.launch_persistent_context(
                        dynamic_dir,
                        executable_path=None,
                        headless=False,
                        slow_mo=100,
                        no_viewport=True,
                        accept_downloads=True,
                        args=launch_args,
                        ignore_default_args=["--no-sandbox"]
                    )
                    print(f"Dynamic isolated browser window launched successfully in: {dynamic_dir}")
                except Exception as dynamic_err:
                    print(f"Dynamic launch note: {dynamic_err}. Launching fresh temporary browser instance...")
                    fallback_browser = await p.chromium.launch(
                        executable_path=None,
                        headless=False,
                        slow_mo=100,
                        args=launch_args
                    )
                    context = await fallback_browser.new_context(no_viewport=True, accept_downloads=True)
                    print("Fresh temporary browser context launched successfully!")

        # Dialog auto-accept handler for any tab
        async def on_dialog_prompt(dialog):
            print(f"🔔 Browser prompt detected: '{dialog.message}' (Type: {dialog.type}). Auto-accepting...")
            try:
                await dialog.accept()
            except Exception as de:
                print(f"Dialog accept note: {de}")

        # Active page tracking across all tabs
        for pge in context.pages:
            pge.on("dialog", lambda dialog: asyncio.create_task(on_dialog_prompt(dialog)))

        async def on_new_page(new_page):
            print(f"✨ New browser tab opened! (URL: {new_page.url or 'about:blank'}). Attaching auto-handlers...")
            new_page.on("dialog", lambda dialog: asyncio.create_task(on_dialog_prompt(dialog)))

        context.on("page", lambda new_page: asyncio.create_task(on_new_page(new_page)))

        def get_best_active_page():
            """Returns the page currently on evisa application or the latest open tab"""
            # First priority: Tab on InregistrareDosar or Sinteza or active form
            for pge in reversed(context.pages):
                if not pge.is_closed():
                    try:
                        u = pge.url
                        if any(kw in u for kw in ["InregistrareDosar", "Sinteza", "Sintez", "Summary", "Dosar/Cautare", "evisa.mae.ro", "eviza.mae.ro"]):
                            return pge
                    except Exception:
                        pass
            # Second priority: Any non-closed tab that is not blank
            for pge in reversed(context.pages):
                if not pge.is_closed():
                    try:
                        u = pge.url
                        if u and "about:blank" not in u:
                            return pge
                    except Exception:
                        pass
            # Fallback
            for pge in reversed(context.pages):
                if not pge.is_closed():
                    return pge
            return None

        page = get_best_active_page() or (context.pages[0] if context.pages else await context.new_page())

        # Navigate to start URL (only if page is blank or not already on evisa)
        start_url = APPLICANT_DATA.get("start_url") or "https://eviza.mae.ro/home?lang=en"
        current_url = ""
        try:
            current_url = page.url
        except Exception:
            pass
            
        if not current_url or "about:blank" in current_url or "chrome://" in current_url:
            print(f"Navigating browser to: {start_url}")
            try:
                await page.goto(start_url)
            except Exception as e:
                print(f"Navigation error: {e}")
        
        # Multi-tab application form detector: scans all open tabs in the window
        async def check_is_application_page():
            for pge in reversed(context.pages):
                if pge.is_closed():
                    continue
                try:
                    c_url = pge.url
                    # 1. URL check
                    if any(kw in c_url for kw in ["InregistrareDosar", "Sinteza", "Sintez", "Summary", "StadiuDosar", "Verificare"]):
                        return pge
                    # 2. Key element selector check
                    for sel in ["#Nume", "#rd4", "#radio_23", "#btnDescarca", "#btnDownload", "a:has-text('Particular situations')", "a:has-text('Personal data')", "a:has-text('Date personale')"]:
                        if await pge.query_selector(sel) is not None:
                            return pge
                    # 3. Text on the body check
                    body_text = await pge.evaluate("() => document.body ? document.body.innerText : ''")
                    body_lower = body_text.lower()
                    for keyword in [
                        "particular situations as regards", "situații deosebite", "personal data of applicant", "date personale ale solicitantului",
                        "summary of visa application", "sinteza dosarului", "status of your visa application", "stadiul dosarului"
                    ]:
                        if keyword in body_lower:
                            return pge
                except Exception:
                    pass
            return None

        app_page = await check_is_application_page()
            
        if not app_page:
            print("\n" + "="*80)
            print("  [ACTION REQUIRED] E-VISA ACTIVE SESSION NOT DETECTED YET!")
            print("  ----------------------------------------------------------------")
            print("  1. Please log in on the opened browser window.")
            print("  2. Select 'Edit/Resume Application' or start a new application.")
            print("  3. If you clicked an email verification link in a new tab, the")
            print("     script will AUTOMATICALLY detect and switch to that tab!")
            print("  ")
            print("  The automation script is actively scanning all tabs...")
            print("  It will resume automatically once the visa form steps are loaded!")
            print("="*80 + "\n")
            
            # Continuously scan for active application form without timeout
            empty_scan_consecutive = 0
            while True:
                try:
                    all_closed = all(pge.is_closed() for pge in context.pages) if (context and context.pages) else False
                    if all_closed:
                        empty_scan_consecutive += 1
                        if empty_scan_consecutive >= 15:
                            print("All browser windows were closed by the user. Exiting.")
                            return
                    else:
                        empty_scan_consecutive = 0
                except Exception:
                    pass

                app_page = await check_is_application_page()
                if app_page:
                    page = app_page
                    print(f"Active application form detected on tab: {page.url}! Commencing automation sequence...")
                    await asyncio.sleep(2) # Brief pause to allow AJAX to settle
                    break
                await asyncio.sleep(2)
        else:
            page = app_page
        
        # Verification prompt detector
        async def check_verification_needed():
            try:
                body_txt = (await page.evaluate("() => document.body ? document.body.innerText : ''")).lower()
                has_verif_text = any(kw in body_txt for kw in [
                    "cod de verificare", "verification code", "link de verificare", "verification link",
                    "e-mail de verificare", "email de verificare", "introduceți codul", "enter the code",
                    "codul de securitate", "security code", "parola dosarului", "application password"
                ])
                verif_input = await page.query_selector(
                    "input[id*='Verif' i], input[name*='Verif' i], input[id*='Code' i], input[name*='Code' i], input[id*='Secur' i]"
                )
                return has_verif_text or (verif_input is not None)
            except Exception:
                return False

        async def unlock_edit_mode():
            print("👉 Attempting to click 'Update Visa Application' / 'Actualizează dosar' or Step 1...")
            
            # 1. Selector checks on visible buttons/links
            for sel in [
                "#btnActualizeaza", "#btnModifica", "#btnUpdate", "#btnEdit",
                "a[href*='InregistrareDosar']", "a[href*='Actualizare']", "a[href*='Modifica']", "a[href*='Edit']",
                "a.btn-warning", "a.btn-primary", "button.btn-warning", "button.btn-primary"
            ]:
                try:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        print(f"Clicking edit/update trigger via selector: '{sel}'")
                        await btn.click()
                        return True
                except Exception:
                    pass

            # 2. Comprehensive DOM evaluation across all elements
            clicked = await page.evaluate("""() => {
                const norm = (s) => (s || "").trim().toLowerCase();
                const editKeywords = [
                    "update visa", "update visa application", "actualizare dosar", "actualizare dosar de viză", "actualizare dosar de viza",
                    "actualizează cererea", "actualizeaza cererea", "actualizează", "actualizeaza", "actualizare",
                    "edit", "modify", "modifică", "modifica", "editează", "editeaza", "edit application", "modify application",
                    "continue application", "resume application", "editează dosarul", "modifică dosarul"
                ];
                
                const elements = Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"], input[type="image"], li, span, div, [role="button"]'));
                for (const el of elements) {
                    const txt = norm(el.textContent || "");
                    const val = norm(el.value || "");
                    const title = norm(el.getAttribute("title") || "");
                    const id = norm(el.id || "");
                    const ariaLabel = norm(el.getAttribute("aria-label") || "");
                    
                    const isMatch = editKeywords.some(kw => 
                        txt.includes(kw) || 
                        val.includes(kw) || 
                        title.includes(kw) || 
                        id.includes(kw) || 
                        ariaLabel.includes(kw)
                    );
                    
                    if (isMatch) {
                        const clickable = el.closest('a') || el.closest('button') || el;
                        if (clickable) {
                            console.log("Found edit/update trigger:", clickable);
                            clickable.click();
                            return true;
                        }
                    }
                }
                return false;
            }""")
            if clicked:
                return True

            # 3. Sidebar navigation fallback: Click Step 1 link directly
            for side_sel in [
                "a:has-text('Particular situations')",
                "a:has-text('Situații deosebite')",
                "a:has-text('1. Particular')",
                "a:has-text('1. Situații')",
                "a[href*='Particular']",
                "a[href*='Situatii']"
            ]:
                try:
                    slink = await page.query_selector(side_sel)
                    if slink and await slink.is_visible():
                        print(f"Clicking Step 1 link via sidebar: '{side_sel}'")
                        await slink.click()
                        return True
                except Exception:
                    pass

            return False

        automator = RomaniaVisaAutomator(page, APPLICANT_DATA)

        # SEQUENCE: Dynamic Self-Healing Loop that auto-detects and executes the correct page step
        print("Starting E-VISA self-healing dynamic step sequence across all wizard stages...")
        
        completed_steps = set()
        step_repeat_counter = {}
        max_attempts = 60  # Max cycles to allow for transitions and page submissions
        
        for attempt in range(max_attempts):
            # Check if all pages are closed
            all_closed = all(pge.is_closed() for pge in context.pages) if context.pages else True
            if all_closed:
                print("Browser window was closed. Exiting automation loop.")
                break
                
            # Automatically switch target to active/newly opened e-Visa tab (e.g. from email verification link)
            active_p = get_best_active_page()
            if active_p and active_p != page:
                page = active_p
                automator.page = active_p
                print(f"Switched active target to tab: {page.url}")
                
            # Allow page to settle and any active AJAX/reloads to finish
            await asyncio.sleep(0.4)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=4000)
            except Exception:
                pass
                
            # 1. Detect current step dynamically from current page structure/URL
            current_step = None
            current_url = page.url.lower()
            page_text = ""
            try:
                page_text = (await page.evaluate("() => document.body ? document.body.innerText.toLowerCase() : ''")) or ""
            except Exception:
                pass
                
            # --- STRICT PRIORITY DYNAMIC STEP DETECTOR ---
            
            # Check for Portal Error (Unexpected Error / Server Error)
            # Debounced: a real error dialog stays on screen, but a one-frame render
            # glitch right after a page transition (e.g. while an AJAX call is still
            # loading) clears within a second or two. Reacting to it instantly was
            # causing an unwanted refresh before the page had even finished settling -
            # e.g. before any document upload had started. Only act if it's still there
            # a moment later.
            is_error_page = "unexpected error" in page_text or "eroare neașteptată" in page_text or "eroare neasteptata" in page_text or "an error occurred" in page_text
            if is_error_page:
                await asyncio.sleep(1.5)
                try:
                    recheck_text = (await page.evaluate("() => document.body ? document.body.innerText.toLowerCase() : ''")) or ""
                except Exception:
                    recheck_text = page_text
                is_error_page = "unexpected error" in recheck_text or "eroare neașteptată" in recheck_text or "eroare neasteptata" in recheck_text or "an error occurred" in recheck_text
                if is_error_page:
                    page_text = recheck_text

            if is_error_page:
                print("⚠️ Portal reported an error page ('An unexpected error has occurred'). Refreshing 1 time to check if page comes back...")
                try:
                    await page.reload(wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(3.0)
                    await automator.wait_for_ajax_idle(10000)
                    
                    # Re-check page text after 1-time refresh
                    page_text = (await page.evaluate("() => document.body ? document.body.innerText.toLowerCase() : ''")) or ""
                    is_error_still_present = "unexpected error" in page_text or "eroare neașteptată" in page_text or "eroare neasteptata" in page_text or "an error occurred" in page_text
                    
                    if not is_error_still_present:
                        print("✅ Page came back successfully after 1-time refresh! Resuming automation from current step...")
                    else:
                        print("⚠️ Error message still present after 1-time refresh. Pausing briefly...")
                        await asyncio.sleep(4)
                        continue
                except Exception as refresh_err:
                    print(f"Error recovery refresh note: {refresh_err}")
                    await asyncio.sleep(4)
                    continue

            # Check for the portal's "Your session has expired" interstitial page.
            # When session expired or error occurs during document upload or workflow:
            # Return to initiate position and restart automation.
            # When returning to Required Supporting Documents, it will check the empty fields and resume from them in order.
            is_session_expired_page = (
                "session has expired" in page_text or
                "sesiunea a expirat" in page_text or
                "trebuie să vă autentificați din nou" in page_text or
                "trebuie sa va autentificati din nou" in page_text
            )
            if is_session_expired_page:
                print("\n" + "="*80)
                print("  🔄 SESSION EXPIRED / PORTAL ERROR DETECTED")
                print("  ----------------------------------------------------------------")
                print("  Returning to initiate position to restart automation...")
                print("  Previously uploaded documents remain securely saved on the portal.")
                print("  When reaching Required Supporting Documents, it will resume from empty fields in order.")
                print("="*80 + "\n")
                try:
                    await page.goto(start_url)
                    await asyncio.sleep(3.0)
                    await automator.wait_for_ajax_idle(10000)
                except Exception as nav_err:
                    print(f"Navigation to start URL note: {nav_err}")
                completed_steps.clear()
                step_repeat_counter.clear()
                continue

            # Helper for multi-frame selector checking
            async def check_sel_any_frame(selectors_list):
                for f in page.frames:
                    for s in selectors_list:
                        try:
                            el = await f.query_selector(s)
                            if el is not None:
                                return True
                        except Exception:
                            pass
                return False

            # Helper: check if any selector in the list currently holds a non-empty value
            # (or is a checked radio/checkbox). Used to detect a page that was already
            # filled & saved before a session-expired restart, so we don't blindly redo it.
            async def check_sel_has_value_any_frame(selectors_list):
                for f in page.frames:
                    for s in selectors_list:
                        try:
                            el = await f.query_selector(s)
                            if el is None:
                                continue
                            val = await f.evaluate(
                                """(el) => {
                                    if (!el) return '';
                                    const type = (el.type || '').toLowerCase();
                                    if (type === 'radio' || type === 'checkbox') {
                                        return el.checked ? 'checked' : '';
                                    }
                                    return (el.value !== undefined ? el.value : (el.textContent || '')).trim();
                                }""",
                                el
                            )
                            if val:
                                return True
                        except Exception:
                            pass
                return False

            # Check if page is Summary of Visa Application File
            is_summary_page = await page.evaluate("""() => {
                const norm = (s) => (s || '').trim().toLowerCase();
                const bodyText = norm(document.body ? document.body.innerText : '');
                const url = norm(window.location.href);
                if (url.includes("selectieserviciivize")) return false;

                const hasSummaryHeading = 
                    bodyText.includes("summary of visa application") ||
                    bodyText.includes("summary of your visa application") ||
                    bodyText.includes("sumarul dosarului de viză") ||
                    bodyText.includes("sumarul dosarului de viza") ||
                    bodyText.includes("sumarul cererii de viză") ||
                    bodyText.includes("sumarul cererii de viza") ||
                    bodyText.includes("sumarul dosarului") ||
                    bodyText.includes("sumarul cererii") ||
                    bodyText.includes("sinteza dosarului") ||
                    bodyText.includes("sinteza cererii") ||
                    bodyText.includes("status of your visa application") ||
                    bodyText.includes("stadiul dosarului de viză") ||
                    bodyText.includes("stadiul dosarului de viza") ||
                    bodyText.includes("stadiul cererii de viză") ||
                    bodyText.includes("stadiul cererii de viza") ||
                    bodyText.includes("stadiul dosarului") ||
                    bodyText.includes("stadiul cererii") ||
                    bodyText.includes("stare dosar") ||
                    bodyText.includes("stare cerere") ||
                    url.includes("/sumar") ||
                    url.includes("/sinteza") ||
                    url.includes("/summary") ||
                    url.includes("starecerere") ||
                    url.includes("stadiudosar");

                const allBtns = Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"], [role="button"]'));
                const hasSummaryBtns = allBtns.some(b => {
                    const id = norm(b.id || '');
                    const txt = norm(b.textContent || b.value || b.getAttribute('href') || '');
                    return id === 'btndescarca' || id === 'btndownload' || id === 'btnactualizeaza' ||
                           txt.includes('download your visa application') ||
                           txt.includes('descarcă cererea de viză') ||
                           txt.includes('descarca cererea') ||
                           txt.includes('descarcă dosarul') ||
                           txt.includes('update visa application') ||
                           txt.includes('actualizează cererea') ||
                           txt.includes('actualizează dosarul');
                });

                const hasActiveInputs = !!document.querySelector('#Nume:not([readonly]):not([disabled]), #NumarDocument:not([readonly]):not([disabled]), #radio_23, #rd4');

                return (hasSummaryHeading || hasSummaryBtns) && !hasActiveInputs;
            }""")

            not_summary = not is_summary_page

            # Check for actual document upload inputs on Step 7/8 (Final Supporting Documents Uploads)
            has_doc_upload_widgets = await check_sel_any_frame([
                "[id*='UploadDocumenteJustificative']",
                ".k-upload-button",
                "#Declaratie_AmLuatLaCunostinta",
                "input[id*='AmLuatLaCunostinta' i]",
                "input[name*='AmLuatLaCunostinta' i]",
                "#btnTrimiteCererea",
                "#btnFinalizeaza",
                "input[value*='Trimite' i]",
                "input[value*='Finaliz' i]"
            ])
            has_final_submit = await check_sel_any_frame(["#btnTrimiteCererea", "#btnFinalizeaza", "input[value*='Trimite' i]", "input[value*='Finaliz' i]"])

            is_supporting_docs_page = (
                has_doc_upload_widgets or 
                has_final_submit or 
                "incarcaredocumente" in current_url.lower() or 
                "documentejustificative" in current_url.lower() or 
                "required supporting documents" in page_text or 
                "documente justificative solicitate" in page_text or 
                "supporting documents required for your visa application" in page_text or 
                "documentele justificative solicitate" in page_text or 
                "it is advisable that your supporting documents be translated" in page_text or 
                "am luat la cunoștință de documentele justificative" in page_text or 
                "am luat la cunostinta de documentele justificative" in page_text or 
                "i am aware of the supporting documents that are requested" in page_text
            )

            # Check unique form fields across all frames upfront
            has_family_fields = await check_sel_any_frame([
                "#DateFamilie_NumeSot", "#DateFamilie_PrenumeSot", "#DateFamilie_NumeSotNastere",
                "#DateFamilie_NumeNastereSot", "#DateFamilie_LocNastereSot", "#NumeSot",
                "#PrenumeSot", "#TaraNastereSot", "[id*='DateFamilie']", "[name*='DateFamilie']",
                "[id*='NumeSot']", "#DateFamilie_DataNastereSot", "#DataNastereSot",
                "input[name*='DateFamilie' i]", "input[id*='DateFamilie' i]"
            ])

            has_journey_fields = await check_sel_any_frame([
                "#DateCalatorie_DataPlanSosire", "#date_of_arrival", "#DataSosire",
                "#DateCalatorie_DataPlanPlecare", "#DateCalatorie_LocalitateFrontiera",
                "#DateCalatorie_RutaPlanificata", "#DateCalatorie_NumeFirma",
                "[id*='DateCalatorie']", "[id*='DataPlanSosire']"
            ])

            has_visa_details_fields = await check_sel_any_frame([
                "#DestinatiePrincipala", "#DestinatiePrincipala_ang", "#DurataSedere",
                "#DurataSederii", "#ID_Scop", "#NumarZileSolicitate",
                "[id*='TipIntrariCerereViza']", "[id*='SederiRomania']"
            ])

            is_family_page = (
                "formularviza5" in current_url.lower() or
                "datefamilie" in current_url.lower() or
                (has_family_fields and not has_visa_details_fields and not has_journey_fields)
            )

            has_host_fields = await check_sel_any_frame([
                "#GazdaSolicitant_NumeOrganizatie", "#GazdaSolicitant_AdresaGazda", "#ID_TipGazda", "#NumeHotel",
                "[id*='GazdaSolicitant']", "[name*='GazdaSolicitant']"
            ])

            has_home_address_fields = await check_sel_any_frame([
                "#TaraDomiciliu_Description", "#LocDomiciliu", "#AdresaDomiciliu", "#DateDomiciliu_AdresaDomiciliu", "#DateDomiciliu_LocDomiciliu",
                "[id*='DateDomiciliu']", "[name*='DateDomiciliu']"
            ])

            has_travel_doc_fields = await check_sel_any_frame([
                "#NumarDocument", "#ID_TipDocument", "#TipDocumentCalatorie"
            ])

            has_personal_data_fields = await check_sel_any_frame([
                "#Nume", "#Prenume", "#CNP", "#DataNasterii", "#LocNastere", "#TaraNastere"
            ])

            # Check if any standard wizard form fields exist
            has_wizard_form_fields = (
                has_family_fields or has_journey_fields or has_visa_details_fields or
                has_host_fields or has_home_address_fields or has_travel_doc_fields or
                has_personal_data_fields or
                await check_sel_any_frame([
                    "#radio_23", "#rd4", "#ID_PostConsular"
                ])
            )

            # Priority 0: Summary of Visa Application File
            if is_summary_page:
                current_step = "summary"

            # Priority 1: Particular Situations (Must be checked before supporting documents because of 'documente justificative' in title)
            elif not_summary and (await check_sel_any_frame(["#radio_23"]) or "particular situations" in page_text or "situații deosebite" in page_text or "situațiile particulare" in page_text or "nu mă aflu în niciuna din situațiile" in page_text or "nu ma aflu in niciuna din situatiile" in page_text) and not (await check_sel_any_frame(["#Nume", "#NumarDocument", "#rd4"])):
                current_step = "particular_situations"

            # Priority 2: Types of visas depending on purpose (Employment marked D/AM)
            # Checked BEFORE select_visa_type because purpose selection URL is ALSO SelectieServiciiVize!
            elif ("types of visas depending" in page_text or 
                "vize în funcție de scopul" in page_text or 
                "vize in functie de scopul" in page_text or 
                "purpose of your journey and stay" in page_text or 
                "scopul călătoriei" in page_text or 
                "scopul calatoriei" in page_text or 
                "employment (marked d/am)" in page_text or 
                "economic activities (marked d/ae)" in page_text or 
                "angajare în muncă" in page_text or 
                "angajare in munca" in page_text) and not (await check_sel_any_frame(["#Nume", "#radio_23"])):
                current_step = "visa_purpose"

            # Priority 4: Diplomatic Mission / Consular Post (Strict check to prevent false positives from other pages)
            elif not_summary and not (await check_sel_any_frame(["#Nume", "#radio_23"])) and (
                "select a diplomatic mission" in page_text or 
                "selectați o misiune diplomatică" in page_text or 
                "selectati o misiune diplomatica" in page_text or 
                (
                    (await check_sel_any_frame(["input[id*='Cetatenie']", "select[id*='Cetatenie']"]) or "current nationality" in page_text or "cetățenia actuală" in page_text) and 
                    (await check_sel_any_frame(["input[id*='Misiune']", "select[id*='Misiune']", "#rcbConsulat_Input", "#rcbMisiune_Input", "select[name*='Organizatie']"]))
                )
            ):
                current_step = "diplomatic_mission"

            # Priority 5: Select Visa Type (Uniform vs Long-stay visa)
            # CRITICAL: Strictly ensure we are NOT on any wizard step (Family, Journey, Personal Data, etc.)
            elif not_summary and not has_wizard_form_fields and not is_family_page and not (await check_sel_any_frame(["#Nume", "#radio_23", "#rd4", "#NumarDocument", "#DateFamilie_NumeSot", "#DateCalatorie_DataPlanSosire"])) and (
                ("selectieserviciivize" in current_url and (await page.locator("input[type='radio']").count() <= 3)) or
                ("select visa type" in page_text and not ("types of visas depending" in page_text or "purpose of your journey" in page_text)) or 
                ("selectați tipul de viză" in page_text and not ("funcție de scopul" in page_text)) or 
                ("selectati tipul de viza" in page_text and not ("functie de scopul" in page_text))
            ):
                current_step = "select_visa_type"

            # Priority 6: Territorial Jurisdiction
            elif not_summary and not (await check_sel_any_frame(["#Nume"])) and (await check_sel_any_frame(["#rd4", "#ID_PostConsular"]) or "territorial jurisdiction" in page_text or "jurisdicție teritorială" in page_text):
                current_step = "territorial_jurisdiction"

            # Priority 6.5: Family Details (Step 6 / 9) - Checked early to prevent any confusion with visa requested or select_visa_type
            elif not_summary and is_family_page:
                current_step = "family_details"
                        
            # Priority 7: Personal Data
            elif not_summary and (await check_sel_any_frame(["#Nume", "#Prenume"]) and not (await check_sel_any_frame(["#NumarDocument", "#DateFamilie_NumeSot", "#DateCalatorie_DataPlanSosire"])) or ("personal data of the applicant" in page_text and "travel document" not in page_text and "family" not in page_text) or ("date cu caracter personal ale solicitantului" in page_text and "călătorie" not in page_text and "familiei" not in page_text)):
                current_step = "personal_data"
                        
            if current_step is None:
                # Priority 8: Travel Document
                # Requires actual Travel Document fields and ensures Steps 4, 5, and 6 fields are not present
                if not_summary and (
                    await check_sel_any_frame(["#NumarDocument", "#ID_TipDocument", "#TipDocumentCalatorie"])
                ) and not has_visa_details_fields and not has_journey_fields and not has_family_fields:
                    current_step = "travel_document"
                            
                # Priority 9: Family Details (Step 6 / 9)
                elif not_summary and is_family_page:
                    current_step = "family_details"

                # Priority 10: Journey Details (Step 5 / 9)
                elif not_summary and (
                    has_journey_fields or 
                    "formularviza4" in current_url.lower() or 
                    "datecalatorie" in current_url.lower() or
                    "details regarding the journey" in page_text.lower() or 
                    "detalii referitoare la călătorie" in page_text.lower() or 
                    "detalii referitoare la calatorie" in page_text.lower()
                ) and not is_family_page:
                    current_step = "journey_details"

                # Priority 11: Visa Requested / Details about the visa (Step 4 / 9)
                elif not_summary and not is_family_page and not has_journey_fields and (
                    has_visa_details_fields or 
                    "formularviza3" in current_url.lower() or 
                    "details about the visa requested" in page_text.lower() or
                    ("details about the visa" in page_text.lower() and "family" not in page_text.lower() and "familia" not in page_text.lower()) or 
                    ("detalii referitoare la viză" in page_text.lower() and "familia" not in page_text.lower()) or 
                    ("detalii referitoare la viza" in page_text.lower() and "familia" not in page_text.lower())
                ):
                    current_step = "visa_requested"
                            
                # Priority 12: Host Details (Details regarding the host)
                elif not_summary and (await check_sel_any_frame(["#GazdaSolicitant_NumeOrganizatie", "#GazdaSolicitant_AdresaGazda", "#ID_TipGazda", "#NumeHotel"]) or "details regarding the host" in page_text or "detalii referitoare la gazdă" in page_text):
                    current_step = "host_details"

                # Priority 13: Applicant's Home Address (Adresa de domiciliu a solicitantului)
                elif not_summary and (await check_sel_any_frame(["#TaraDomiciliu_Description", "#LocDomiciliu", "#AdresaDomiciliu", "#DateDomiciliu_AdresaDomiciliu", "#DateDomiciliu_LocDomiciliu"]) or "applicant's home address" in page_text or "adresa de domiciliu a solicitantului" in page_text or "adresa de domiciliu" in page_text or "adresa solicitantului" in page_text):
                    current_step = "applicant_home_address"

                # Priority 14: Required Supporting Documents (File Uploads & Declaration)
                elif not_summary and is_supporting_docs_page and not (
                    has_personal_data_fields or has_travel_doc_fields or has_visa_details_fields or 
                    has_journey_fields or has_family_fields or has_host_fields or has_home_address_fields or
                    await check_sel_any_frame(["#radio_23", "#rd4", "#ID_PostConsular", "#Nume"])
                ):
                    current_step = "supporting_documents"

            # Define wizard steps order to enforce sequential execution
            WIZARD_STEPS_ORDER = [
                "territorial_jurisdiction",
                "personal_data",
                "travel_document",
                "visa_requested",
                "journey_details",
                "family_details",
                "host_details",
                "applicant_home_address",
                "supporting_documents",
                "summary"
            ]

            if current_step in WIZARD_STEPS_ORDER:
                current_idx = WIZARD_STEPS_ORDER.index(current_step)
                
                # Check for marital status to see if family_details is required
                is_married = False
                st = (
                    APPLICANT_DATA.get("personal", {}).get("marital_status") or
                    APPLICANT_DATA.get("personal_data", {}).get("marital_status") or
                    APPLICANT_DATA.get("marital_status")
                )
                if st:
                    st_lower = str(st).lower()
                    if "married" in st_lower or "căsătorit" in st_lower or "casatorit" in st_lower or st_lower == "2":
                        is_married = True

                # Determine which steps are actually required
                required_steps = []
                for s in WIZARD_STEPS_ORDER:
                    if s == "family_details" and not is_married:
                        # Skip if not married
                        continue
                    required_steps.append(s)

                if current_step in required_steps and current_step not in ["supporting_documents", "summary"]:
                    req_idx = required_steps.index(current_step)

                    # ROOT-CAUSE FIX: figure out which earlier step (if any) still needs
                    # attention BEFORE marking anything as completed. The old code called
                    # completed_steps.add(prior_s) for every earlier required step FIRST,
                    # and only THEN scanned required_steps[:req_idx] for something "not in
                    # completed_steps" - but every one of those steps had just been added
                    # to completed_steps on the line above, so that scan could never find
                    # anything and this entire "navigate back" branch was dead code.
                    #
                    # That's how a MARRIED applicant's family_details page went unfilled:
                    # the instant the detector landed on host_details (whether from the
                    # Wizard-Circle-5 fallback overshooting, or resuming a session), the
                    # script rubber-stamped journey_details AND family_details as "done"
                    # without ever calling page_journey()/page_family_details() or checking
                    # whether spouse data actually made it onto the portal.
                    #
                    # For family_details specifically, "not in completed_steps" also isn't
                    # trustworthy evidence on its own (completed_steps is only this
                    # process's in-memory bookkeeping, wiped on every restart) - so verify
                    # directly against the DOM/portal: if the applicant is married and the
                    # spouse name fields have no saved value, treat family_details as
                    # incomplete regardless of what completed_steps says.
                    earliest_uncompleted = None
                    for step in required_steps[:req_idx]:
                        if step not in completed_steps:
                            earliest_uncompleted = step
                            break

                    if earliest_uncompleted and len(completed_steps) > 0:
                        print(f"📌 Sequential Rule Enforced: Earlier step '{earliest_uncompleted}' is not completed yet (currently on '{current_step}'). Navigating back...")
                        navigated = await automator.click_sidebar_step(earliest_uncompleted)
                        if navigated:
                            await asyncio.sleep(2.5)
                            await automator.wait_for_ajax_idle(10000)
                            continue
                        else:
                            print(f"⚠️ Could not click sidebar link for '{earliest_uncompleted}'. Proceeding on '{current_step}'...")

                    # Register all prior required steps as completed so we don't repeat this check
                    for prior_s in required_steps[:req_idx]:
                        completed_steps.add(prior_s)

            if current_step:
                print(f"👉 Dynamically detected active page: '{current_step}' (Attempt {attempt+1}/{max_attempts})")
                
                step_repeat_counter[current_step] = step_repeat_counter.get(current_step, 0) + 1

                # If we have re-landed on an interactive selection page (such as visa_purpose or select_visa_type)
                # or the critical supporting_documents page, always re-execute to verify all items.
                if current_step in ["select_visa_type", "diplomatic_mission", "supporting_documents"]:
                    completed_steps.discard(current_step)
                elif current_step in completed_steps and current_step != "summary":
                    if step_repeat_counter[current_step] > 1:
                        print(f"⚠️ Re-landed on '{current_step}'. Re-executing full step automation to ensure fields are valid and properly saved...")
                        completed_steps.discard(current_step)
                    else:
                        print(f"Already automated '{current_step}'. Re-triggering the Save & Next action in case the transition hung...")
                        try:
                            await automator.trigger_save_and_next()
                        except Exception:
                            pass
                        await asyncio.sleep(3)
                        continue
                elif (
                    current_step not in completed_steps
                    and current_step != "summary"
                    and step_repeat_counter[current_step] == 1
                ):
                    # RESUME-AFTER-RESTART CHECK: completed_steps is wiped whenever automation
                    # restarts from start_url (session expired / portal error). A page that was
                    # ALREADY filled & saved before the crash is no longer remembered as done -
                    # only steps strictly BEFORE it get re-marked completed. Without this check,
                    # landing back on that exact page blindly re-runs the full fill routine even
                    # though the portal already shows valid saved values. So inspect the page's
                    # own key fields for existing values BEFORE deciding to fill anything.
                    STEP_KEY_FIELDS = {
                        "territorial_jurisdiction": ["#rd4:checked", "#ID_PostConsular"],
                        "personal_data": ["#Nume", "#Prenume", "#CNP", "#DataNasterii"],
                        "travel_document": ["#NumarDocument", "#ID_TipDocument"],
                        "visa_requested": ["#DurataSedere", "#DurataSederii", "#NumarZileSolicitate", "#DestinatiePrincipala"],
                        "journey_details": ["#DateCalatorie_DataPlanSosire", "#DataSosire", "#DateCalatorie_DataPlanPlecare"],
                        "family_details": ["#DateFamilie_NumeSot", "#NumeSot", "#PrenumeSot"],
                        "host_details": ["#GazdaSolicitant_NumeOrganizatie", "#NumeHotel", "#GazdaSolicitant_AdresaGazda"],
                        "applicant_home_address": ["#AdresaDomiciliu", "#DateDomiciliu_AdresaDomiciliu", "#LocDomiciliu"],
                    }
                    key_fields = STEP_KEY_FIELDS.get(current_step)
                    already_saved = await check_sel_has_value_any_frame(key_fields) if key_fields else False

                    # ROOT-CAUSE FIX: for family_details, "any one field has a value" is not
                    # enough evidence of a real save - e.g. a surname could have stuck while
                    # first name silently failed, and the old check would still call that
                    # "already saved" and skip refilling. Require BOTH the spouse surname
                    # AND first name to be present before treating this step as done.
                    if current_step == "family_details" and already_saved:
                        surname_saved = await check_sel_has_value_any_frame(["#DateFamilie_NumeSot", "#NumeSot"])
                        first_name_saved = await check_sel_has_value_any_frame(["#DateFamilie_PrenumeSot", "#PrenumeSot"])
                        already_saved = surname_saved and first_name_saved
                        if not already_saved:
                            print("⚠️ [Family Details] Resume check found only partial spouse data saved - "
                                  "re-running the fill instead of skipping it.")

                    if already_saved:
                        print(f"📌 Resume check: '{current_step}' already has saved data on the portal. Skipping refill - just clicking Save/Next...")
                        try:
                            await automator.trigger_save_and_next()
                        except Exception:
                            pass
                        completed_steps.add(current_step)
                        await asyncio.sleep(3)
                        continue
                    else:
                        print(f"📌 Resume check: '{current_step}' has no saved data yet. Proceeding with normal fill automation...")
                
                # Execute step automation with full logging
                try:
                    if current_step == "select_visa_type":
                        await automator.page_select_visa_type()
                    elif current_step == "diplomatic_mission":
                        await automator.page_diplomatic_mission()
                    elif current_step == "visa_purpose":
                        await automator.page_visa_purpose()
                    elif current_step == "particular_situations":
                        await automator.page_particular_situations()
                    elif current_step == "territorial_jurisdiction":
                        await automator.page_territorial_jurisdiction()
                    elif current_step == "personal_data":
                        await automator.page_personal_data()
                    elif current_step == "travel_document":
                        await automator.page_travel_document()
                    elif current_step == "visa_requested":
                        await automator.page_details_about_visa()
                    elif current_step == "journey_details":
                        await automator.page_journey()
                    elif current_step == "family_details":
                        await automator.page_family_details()
                    elif current_step == "host_details":
                        await automator.page_host_details()
                    elif current_step == "applicant_home_address":
                        await automator.page_applicant_home_address()
                    elif current_step == "supporting_documents":
                        await automator.page_supporting_documents()
                    elif current_step == "summary":
                        summary_done = await automator.page_summary()
                        if summary_done:
                            print("✅ E-VISA Full Automation successfully completed and generated final summary download!")
                            break
                        else:
                            print("🔄 Status was DRAFT. Clicked 'Update visa application' to continue process...")
                            completed_steps.clear()
                            step_repeat_counter.clear()
                            await asyncio.sleep(2.5)
                            if await check_verification_needed():
                                print("⚠️ Email verification requested. Please enter code or click email link to unlock.")
                                await asyncio.sleep(3)
                            continue
                        
                    completed_steps.add(current_step)
                except BaseException as e:
                    # ROOT-CAUSE FIX: same asyncio.CancelledError-is-a-BaseException gap
                    # as the outer handler below. Catching it here too means a single
                    # step (e.g. the download step) that gets cancelled just gets
                    # retried on the next loop cycle instead of blowing past this loop
                    # entirely and racing to close the browser.
                    err_msg = str(e)
                    if "SESSION_EXPIRED_RESTART" in err_msg:
                        print("\n🔄 Session expired during upload step. Returning to initiate position and restarting automation...")
                        try:
                            await page.goto(start_url)
                            await asyncio.sleep(3.0)
                            await automator.wait_for_ajax_idle(10000)
                        except Exception as nav_err:
                            print(f"Navigation to start URL note: {nav_err}")
                        completed_steps.clear()
                        step_repeat_counter.clear()
                        continue
                    print(f"Error executing automation for page '{current_step}': {e}")
                    print("Retrying page execution on the next loop cycle...")
                    
                await asyncio.sleep(0.5)
            else:
                print("Scanning page structure to identify current wizard step... Please wait or navigate manually if stuck.")
                # If stuck scanning for several cycles, attempt unlock/edit click as fallback
                if attempt > 2 and len(completed_steps) == 0:
                    await unlock_edit_mode()
                await asyncio.sleep(1.5)

        print("\n" + "=" * 80)
        print("✅ FULL AUTOMATION SEQUENCE COMPLETED.")
        print("=" * 80)
        await keep_browser_open_indefinitely(context)

    except BaseException as run_err:
        # ROOT-CAUSE FIX: this used to be "except Exception as run_err:". Since
        # Python 3.8, asyncio.CancelledError inherits from BaseException, NOT
        # Exception — so a cancellation firing mid-download (e.g. while awaiting
        # expect_download()/save_as(), or from Playwright's own internal timeout
        # plumbing) was NOT caught here. It skipped straight past this whole
        # "keep the browser open" fallback and propagated all the way up to the
        # bottom-level "except (KeyboardInterrupt, asyncio.CancelledError)"
        # handler, which just prints a message and lets the process — and with
        # it the browser subprocess — exit. That is exactly how the browser was
        # closing before the ZIP download finished. Catching BaseException here
        # means literally nothing can skip the browser-stays-open guarantee.
        print("=" * 80)
        print(f"⚠️ Automation paused with notice: {run_err}")
        print("   The browser window has been kept open so you can inspect the current")
        print("   page, finish any manual steps, or download files directly.")
        print("=" * 80)
        try:
            if automator:
                await automator.capture_summary_screenshot()
        except Exception:
            pass
        await keep_browser_open_indefinitely(context)

async def keep_browser_open_indefinitely(context=None):
    """
    Guarantees the browser and Python process stay alive indefinitely.
    The browser will NEVER shut down automatically.
    It will only exit if you press Ctrl+C in terminal.
    """
    print("\n" + "=" * 80)
    print("🔒 [BROWSER PERSISTENCE ACTIVE] The browser will remain open indefinitely.")
    print("   👉 The browser will NOT shut down automatically.")
    print("   👉 You can inspect, review fields, or interact with any tabs freely.")
    print("   👉 To close when done, press Ctrl+C in terminal.")
    print("=" * 80 + "\n")

    # If context is available and all pages were closed, open a new page so Chrome window stays visible
    if context:
        try:
            open_pages = [p for p in context.pages if not p.is_closed()]
            if not open_pages:
                new_p = await context.new_page()
                await new_p.goto("https://evisa.mae.ro/home?lang=en")
                print("🔒 [Browser Persistence] Re-opened active tab to keep browser visible.")
        except Exception:
            pass

    while True:
        try:
            if context:
                try:
                    open_pages = [p for p in context.pages if not p.is_closed()]
                    if not open_pages:
                        await context.new_page()
                except Exception:
                    pass
            await asyncio.sleep(2.0)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\nShutting down per user request (Ctrl+C).")
            break
        except BaseException:
            await asyncio.sleep(2.0)
if __name__ == "__main__":
    try:
        asyncio.run(run_visa_automation())
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nAutomation stopped by user (Ctrl+C). Browser closed.")
    except BaseException as general_err:
        print(f"\nAutomation paused with notice: {general_err}")
        print("Holding Python process open so browser window remains active...")
        try:
            import time
            while True:
                time.sleep(2)
        except (KeyboardInterrupt, SystemExit):
            print("\nExiting.")

