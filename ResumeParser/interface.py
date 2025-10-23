from copy import deepcopy
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import subprocess
from docx import Document
import fitz
import streamlit as st
import re
from filtering_cv import rank_with_bm25_and_sbert
from jd_prompt import post_parse_jd
from export_resume import create_docx_file, post_process
from prompt import post_add_skills, post_rewrite_task, post_write_description, prompt_to_add_skills, prompt_to_rewrite_task, prompt_to_write_description
from text_extraction import get_text_from_file, process_and_parse_cv, process_and_parse_jd
from llm_utils import call_gemini
from rag import build_rag_pipeline
import pythoncom
import threading


from docx2pdf import convert  # Add this import for DOCX to PDF conversion
# Place this entire block after your imports at the top of your script

# Custom CSS

st.markdown("""
<style>
    /* Class container cho popover (hộp chat nổi) */
    .floating-chat {
    position: fixed !important; /* Giữ cố định trên màn hình */
    bottom: 20px !important;    /* Cách mép dưới 20px */
    right: 20px !important;     /* Cách mép phải 20px */
    left: auto !important;      /* Xóa mọi ảnh hưởng của left */
    z-index: 9999 !important;   /* Đảm bảo nổi trên cùng */
}           
    /* CSS cho nút bấm bên trong floating-chat */
    .floating-chat button {
        border-radius: 50%;    /* Làm nút thành hình tròn */
        width: 55px;           /* Chiều rộng 55px */
        height: 55px;          /* Chiều cao 55px */
        font-size: 24px;       /* Kích thước chữ hoặc icon bên trong nút */
        box-shadow: 2px 2px 8px rgba(0,0,0,0.2); /* Đổ bóng, tạo hiệu ứng nổi */
    }
""", unsafe_allow_html=True)


def write_description(i):
    st.toast("Summarizing description ...", icon='✍️')
    
    resp = st.session_state.get(f"work_responsibilities_{i}", "")
    title = st.session_state.get(f"work_title_{i}", "employee")
    company = st.session_state.get(f"work_company_{i}", "Conpany")
    description = st.session_state.get(f"work_description_{i}", "")
    
    prompt = prompt_to_write_description(
        resp=resp, title=title, company=company, description=description
    )
    new_output = call_gemini(f"You are a career consultant.\n\n{prompt}")

    new_output = post_write_description(new_output)
    st.session_state[f"work_description_{i}"] = new_output
    autofilled_work_exp[i]["work_description"]  = st.session_state[f"work_description_{i}"]

def rewrite_resp(i):
    st.toast("Rewriting responsibilities ...", icon='✍️')
    
    resp = st.session_state.get(f"work_responsibilities_{i}", "")
    print (resp)
    title = st.session_state.get(f"work_title_{i}", "employee")
    print (title)
    company = st.session_state.get(f"work_company_{i}", "Conpany")
    print(company)
    description = st.session_state.get(f"work_description_{i}", "")
    print(description)

    prompt = prompt_to_rewrite_task(
        resp=resp, title=title, company=company, description=description
    )

    new_output = call_gemini(f"You are a career consultant.\n\n{prompt}")

    new_output = post_rewrite_task(new_output)
    st.session_state[f"work_responsibilities_{i}"] = new_output
    autofilled_work_exp[i]["work_responsibilities"]  = st.session_state[f"work_responsibilities_{i}"]


def infer_more_skills():
    st.toast("Searching for more skills...", icon="🔎")
    export_skills = []
    for i in range(len(autofilled_skills)):
        es = {
            "skill_name": st.session_state[f"skill_name_{i}"],
        }
        export_skills.append(es)
    skills = '\n'.join(f"{c['skill_name']}" for c in export_skills)
    
    prompt = prompt_to_add_skills(skills=skills, resume_json=str(st.session_state['parsed_pdf']))
    new_skills = call_gemini(f"You are a career consultant.\n\n{prompt}")
    new_skills = post_add_skills(new_skills)

    # 🔹 Làm sạch chuỗi trả về
    cleaned = new_skills.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json", "").strip()

    try:
        new_skills = json.loads(cleaned)   # an toàn hơn eval
    except Exception as e:
        st.error(f"Không parse được skills: {e}")
        new_skills = []

    st.session_state['new_skills'] = new_skills


def convert_docx_to_pdf(file_bytes):
    # Tạo file tạm docx

    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_docx:
        tmp_docx.write(file_bytes)
        tmp_docx_path = tmp_docx.name

    tmp_pdf_path = tmp_docx_path.replace(".docx", ".pdf")

    # Khởi tạo COM + chuyển đổi
    pythoncom.CoInitialize()
    try:
        convert(tmp_docx_path, tmp_pdf_path)
    finally:
        pythoncom.CoUninitialize()

    # Đọc pdf ra bytes
    with open(tmp_pdf_path, "rb") as f:
        pdf_bytes = f.read()

    # Cleanup thủ công
    try:
        os.remove(tmp_docx_path)
        os.remove(tmp_pdf_path)
    except Exception as e:
        print("Cleanup error:", e)
    return pdf_bytes


def display_file(file_bytes: bytes, file_type: str):
    """
    Preview file (chỉ còn xử lý PDF). 
    Nếu là DOCX thì convert sang PDF trước rồi hiển thị như PDF.
    """
    if file_type.lower() == "docx":
        file_bytes = convert_docx_to_pdf(file_bytes)
        file_type = "pdf"

    if file_type.lower() == "pdf":
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        image_list = []
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            image_list.append(img_bytes)
        doc.close()
        st.image(image_list)
    else:
        st.warning("File type is not supported.")

    st.session_state['uploaded'] = True

def reset_description(i): # reset về nguyên gốc ban đầu 
    description = work_exp[i].get("work_description", "") 
    st.session_state[f"work_description_{i}"] = description
    st.toast('Description restored.', icon='🔄')

def reset_resp(i):
    resps_list = work_exp[i].get("work_responsibilities", []) 
    resps_str = "\n".join([f"- {c}" for c in resps_list])
    st.session_state[f"work_responsibilities_{i}"] = resps_str
    st.toast('Responsibilities restored.', icon='🔄')


def submit_form(uploaded_file_bytes=None, uploaded_file_type=None):
    autofilled_work_exp = globals().get("autofilled_work_exp", [])
    autofilled_edus = globals().get("autofilled_edus", [])
    autofilled_projects = globals().get("autofilled_projects", [])
    autofilled_skills = globals().get("autofilled_skills", [])
    autofilled_languages = globals().get("autofilled_languages", [])

    if "birth_year" not in st.session_state:
        st.session_state.birth_year = ""
    if "gender" not in st.session_state:
        st.session_state.gender = ""
    if "phone" not in st.session_state:
        st.session_state.phone = ""
    if "email" not in st.session_state:
        st.session_state.email = ""
    if "address" not in st.session_state:
        st.session_state.address = ""


    # ===== Work Experience =====
    export_work_exp = []
    for i in range(len(autofilled_work_exp)):
        ewe = {
            "work_timeline": [
                st.session_state[f"work_timeline_from_{i}"],
                st.session_state[f"work_timeline_to_{i}"]
            ],
            "work_company": st.session_state[f"work_company_{i}"],
            "work_title": st.session_state[f"work_title_{i}"],
            "work_description": st.session_state[f"work_description_{i}"],
            "work_responsibilities": [
                c[2:] for c in st.session_state[f"work_responsibilities_{i}"].split('\n')
            ],
            "work_technologies": st.session_state[f"work_technologies_{i}"]
        }
        export_work_exp.append(ewe)

    # ===== Education =====
    export_education = []
    for i in range(len(autofilled_edus)):
        ee = {
            "edu_timeline": [
                st.session_state[f"edu_timeline_from_{i}"],
                st.session_state[f"edu_timeline_to_{i}"]
            ],
            "edu_school": st.session_state[f"edu_school_{i}"],
            "edu_degree": st.session_state[f"edu_degree_{i}"],
            "edu_gpa": st.session_state[f"edu_gpa_{i}"],
            "edu_description": st.session_state[f"edu_description_{i}"],
        }
        export_education.append(ee)

    # ===== Projects =====
    export_projects = []
    for i in range(len(autofilled_projects)):
        ep = {
            "project_timeline": [
                st.session_state[f"project_timeline_from_{i}"],
                st.session_state[f"project_timeline_to_{i}"]
            ],
            "project_name": st.session_state[f"project_name_{i}"],
            "project_description": st.session_state[f"project_description_{i}"],
            "project_responsibilities": [
                c[2:] for c in st.session_state[f"project_responsibilities_{i}"].split('\n')
            ],
            "project_technologies": st.session_state[f"project_technologies_{i}"]
        }
        export_projects.append(ep)

    # ===== Skills =====
    export_skills = []
    for i in range(len(autofilled_skills)):
        es = {"skill_name": st.session_state[f"skill_name_{i}"]}
        export_skills.append(es)

    # ===== Languages =====
    export_languages = []
    for i in range(len(autofilled_languages)):
        el = {
            "lang": st.session_state[f"lang_{i}"],
            "lang_lvl": st.session_state[f"lang_lvl_{i}"],
        }
        export_languages.append(el)

    # ===== Final Export =====
    export = {
        "candidate_name": st.session_state.candidate_name,
        "candidate_title": st.session_state.candidate_title,
        "birth_year": st.session_state.birth_year,
        "gender": st.session_state.gender,
        "phone": st.session_state.phone,
        "email": st.session_state.email,
        "address": st.session_state.address,
        "summary": st.session_state.summary,
        "links": st.session_state.links.split('\n'),
        "languages": export_languages,
        "work_exp": export_work_exp,
        "education": export_education,
        "projects": export_projects,
        "certifications": st.session_state.certifications.split('\n'),
        "skills": export_skills
    }

    st.session_state['output_json'] = export

    if uploaded_file is not None:
    # Lấy tên file gốc từ file upload
        cv_name = os.path.splitext(uploaded_file.name)[0]  # tên file không có đuôi
        candidate_name = export.get("candidate_name", "").replace(" ", "_") or "unknown"

        # Tạo folder output/<tên file upload>/cv_<candidate_name>
        output_dir = os.path.join("output", cv_name, f"cv_{candidate_name}")

        # Xóa folder cũ nếu tồn tại
        if os.path.exists(output_dir):
            try:
                shutil.rmtree(output_dir)
            except PermissionError:
                st.warning(f"Không thể xóa folder cũ: {output_dir}, có thể đang mở ở nơi khác!")

    # Tạo folder mới
    os.makedirs(output_dir, exist_ok=True)

    # ===== Lưu JSON =====
    json_path = os.path.join(output_dir, "export_resume.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=4)

    # ===== Lưu TXT cho chatbot =====
    txt_path = os.path.join(output_dir, "export_resume_for_chatbot.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        # Thông tin cơ bản
        f.write(f"# {export.get('candidate_name', 'N/A')}\n")
        f.write(f"{export.get('candidate_title', '')}\n\n")
        f.write(f"# {export.get('birth_year', 'N/A')}\n")
        f.write(f"#{export.get('gender', '')}\n\n")
        f.write(f"# {export.get('email', 'N/A')}\n")
        f.write(f"#{export.get('address', '')}\n\n")
        f.write(f"#{export.get('phone', '')}\n\n")

        # Tóm tắt
        if export.get("summary"):
            f.write("## Summary\n")
            f.write(f"{export['summary']}\n\n")

        # Ngôn ngữ
        if export.get("languages"):
            f.write("## Languages\n")
            for lang_info in export["languages"]:
                f.write(f"- {lang_info.get('lang', '')}: {lang_info.get('lang_lvl', '')}\n")
            f.write("\n")

        # Kinh nghiệm làm việc
        if export.get("work_exp"):
            f.write("## Work Experience\n")
            for work in export["work_exp"]:
                timeline = f"({work.get('work_timeline', ['',''])[0]} - {work.get('work_timeline', ['',''])[1] or 'Present'})"
                f.write(f"### {work.get('work_title', 'N/A')} at {work.get('work_company', 'N/A')} {timeline}\n")
                if work.get("work_description"):
                    f.write(f"- Description: {work['work_description']}\n")
                if work.get("work_responsibilities"):
                    f.write("- Responsibilities:\n")
                    for resp in work["work_responsibilities"]:
                        f.write(f"  - {resp}\n")
                if work.get("work_technologies"):
                    f.write(f"- Technologies: {work['work_technologies']}\n")
                f.write("\n")

        # Học vấn
        if export.get("education"):
            f.write("## Education\n")
            for edu in export["education"]:
                timeline = f"({edu.get('edu_timeline', ['',''])[0]} - {edu.get('edu_timeline', ['',''])[1] or 'Present'})"
                f.write(f"### {edu.get('edu_school', 'N/A')} {timeline}\n")
                f.write(f"- Degree: {edu.get('edu_degree', '')}\n")
                if edu.get("edu_gpa"):
                    f.write(f"- GPA: {edu['edu_gpa']}\n")
                if edu.get("edu_description"):
                    f.write(f"- Description: {edu['edu_description']}\n")
                f.write("\n")

        # Dự án
        if export.get("projects"):
            f.write("## Projects\n")
            for proj in export["projects"]:
                timeline = f"({proj.get('project_timeline', ['',''])[0]} - {proj.get('project_timeline', ['',''])[1]})"
                f.write(f"### {proj.get('project_name', 'N/A')} {timeline}\n")
                if proj.get("project_description"):
                    f.write(f"- Description: {proj['project_description']}\n")
                if proj.get("project_responsibilities"):
                    f.write("- Responsibilities:\n")
                    for resp in proj["project_responsibilities"]:
                        f.write(f"  - {resp}\n")
                if proj.get("project_technologies"):
                    f.write(f"- Technologies: {proj['project_technologies']}\n")
                f.write("\n")

        # Kỹ năng
        if export.get("skills"):
            f.write("## Skills\n")
            skill_names = [skill.get('skill_name', '') for skill in export['skills']]
            f.write(", ".join(skill_names) + "\n")
            f.write("\n")
        # Chứng chỉ
        if export.get("certifications"):
            f.write("## Certifications\n")
            for cert in export["certifications"]:
                f.write(f"- {cert}\n")
            f.write("\n")
    # ===== Nếu file gốc là PDF thì lưu thêm ảnh từng trang =====

    uploaded_file_bytes = st.session_state.get("uploaded_file_bytes")
    uploaded_file_type = st.session_state.get("uploaded_file_type")

    if uploaded_file_bytes and uploaded_file_type and "pdf" in uploaded_file_type.lower():
        doc = fitz.open(stream=uploaded_file_bytes, filetype="pdf")
        print("Uploaded file type:", uploaded_file_type)
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=200)
            img_path = os.path.join(output_dir, f"page_{i+1}.png")
            pix.save(img_path)
            print(f"Saved: {img_path}")
        doc.close()
    st.session_state["uploaded_file_bytes"] = None
    st.session_state["uploaded_file_type"] = None
    st.toast("Form submitted and files saved!", icon="🎯")

    st.toast("Preparing chatbot...", icon="🤖")
    
    # 1. Đọc lại nội dung file txt vừa tạo
    with open(txt_path, "r", encoding="utf-8") as f:
        cv_text_content = f.read()

    # 2. Gọi hàm build_rag_pipeline từ rag.py
    # Truyền thêm output_dir để lưu các file chunk (nếu muốn)
    qa_chain = build_rag_pipeline(cv_text_content, output_dir)
    
    # 3. Lưu pipeline vào session_state để giao diện sử dụng
    st.session_state.qa_chain = qa_chain
    
    # 4. Khởi tạo hoặc xóa lịch sử chat cũ
    st.session_state.messages = []
    
    if qa_chain:
        st.toast("Chatbot is ready!", icon="✅")
    else:
        st.toast("Failed to initialize chatbot.", icon="❌")

def downloader_callback(): # download kết quả json cuối 
    if st.session_state['output_json'] is None:
        st.toast(":red[Submit the form first!]", icon="⚠️")
        return
    st.toast("New resume downloaded!", icon="🎯") 

def uploader_callback(): # reset pipeline xử lý CV mới
    st.toast("Resume uploaded.", icon="📑")

    st.session_state['parsed_pdf'] = dict()
    st.session_state['processed'] = False
    st.session_state['output_json'] = None
    st.session_state['new_skills'] = []
    st.session_state['candidate_title'] = None
    st.session_state['messages'] = []
    st.session_state['qa_chain'] = None


def init_state(key, value):
    if key not in st.session_state:
        st.session_state[key] = value

init_state('parsed_pdf', dict())
init_state('uploaded', False)
init_state('processed', False)
init_state('output_json', None)



st.set_page_config(page_title="Resume Parser & CV Filtering", page_icon="📑", layout="wide")

# Khởi tạo session_state để lưu trang hiện tại
# Mặc định sẽ là trang 'Resume Parser'
if 'page' not in st.session_state:
    st.session_state.page = 'Resume Parser'

# Tạo nút radio trong sidebar để chọn chức năng
with st.sidebar:
    st.session_state.page = st.radio(
        "Choose function",
        ['Resume Parser', 'Filter CVs']
    )
    st.markdown("---") # Thêm một đường kẻ để phân cách
if st.session_state.page == 'Resume Parser':
    st.set_page_config(page_title="Resume Parser", page_icon="📑")
    st.title("📑 Resume Parser")


    # st.button("Restart", on_click="restart")
    #upload file
    with st.sidebar:
        uploaded_file = st.file_uploader("Upload file PDF or DOCX", on_change=uploader_callback)

        if uploaded_file is not None:
            file_bytes = uploaded_file.read()
            if uploaded_file.name.lower().endswith(".pdf"):
                st.session_state["uploaded_file_bytes"] = file_bytes
                st.session_state["uploaded_file_type"] = uploaded_file.type
                display_file(file_bytes, 'pdf')
            elif uploaded_file.name.lower().endswith(".docx"):
                display_file(file_bytes, 'docx')
            else:
                st.warning("Chỉ hỗ trợ PDF và DOCX")
        else:
            st.info("Please upload file.")

    

    if uploaded_file is not None and not st.session_state.get('processed', False):
    # Trạng thái: đang xử lý
        status_placeholder = st.empty()
        with status_placeholder:
            status_process = st.status("Processing the resume ...", expanded=True)
            uploaded_file.seek(0)
            file_bytes = uploaded_file.read()
            filename = uploaded_file.name

            status_process.write("👩‍💻 Extracting raw text from the resume...")
            # Bước 1: Chỉ trích xuất văn bản thô.
            cv_text = get_text_from_file(file_bytes, filename, file_role="cv")
            
            status_process.write("🤖 Analyzing and parsing the resume...")
            # Bước 2: Xử lý và parse CV từ văn bản thô đó.
            parsed_data = process_and_parse_cv(cv_text, filename)

            st.session_state['parsed_pdf'] = parsed_data
            st.session_state['processed'] = True
            status_process.update(label="Completed", state="complete", expanded=False)
            st.success("Resume processed! You can edit the information now.", icon="✅")
        status_placeholder.empty()
    # Nếu đã xử lý xong thì hiển thị form nhập liệu

    if st.session_state.get('processed', False): 
        header = st.container()
        with header:
            tab_info, tab_chat = st.tabs(["📄 Resume Info", "🤖 Chatbot"])
            st.write("""<div class='fixed-header'/>""", unsafe_allow_html=True)
        with tab_info:
            with st.expander(label="INFORMATION", expanded=True):
                st.markdown("""---""")

                # Lấy data từ session_state
                parsed_data = st.session_state.get("parsed_pdf", {})
                st.session_state.candidate_title = parsed_data.get("candidate_title", "")
                st.session_state.birth_year = parsed_data.get("birth_year", "")
                st.session_state.gender = parsed_data.get("gender", "")
                st.session_state.phone = parsed_data.get("phone", "")
                st.session_state.email = parsed_data.get("email", "")
                st.session_state.address = parsed_data.get("address", "")
                # Basic info
                candidate_name = st.text_input(
                    'Name',
                    value=parsed_data.get('candidate_name', ""),
                    key="candidate_name"
                )
                candidate_title = st.text_input(
                    'Title',
                    value=parsed_data.get('candidate_title', ""),
                    key="candidate_title"
                )
                summary = st.text_area(
                    'Summary',
                    value=parsed_data.get('summary', ""),
                    key="summary"
                )

                # Links
                links_str = st.text_area(
                    "🔗 Links",
                    value="\n".join(parsed_data.get("links", [])),
                    key="links"
                )

                # Languages
                languages = parsed_data.get('languages', [])
                st.markdown("#### 🌐 Languages")
                if languages:
                    for l in languages:
                        st.write(f"{l.get('lang', '')} — {l.get('lang_lvl', '')}")

                autofilled_languages = deepcopy(languages)
                c1, c2 = st.columns([3, 2])
                for i, lg in enumerate(languages):
                    visibility = "visible" if i == 0 else "hidden"
                    lang = c1.text_input(
                        "Language",
                        value=lg.get("lang", ""),
                        label_visibility=visibility,
                        key=f"lang_{i}"
                    )
                    lang_lvl = c2.text_input(
                        "Level",
                        value=lg.get("lang_lvl", ""),
                        label_visibility=visibility,
                        key=f"lang_lvl_{i}"
                    )
                    autofilled_languages[i] = {"lang": lang, "lang_lvl": lang_lvl}

                # Update lại state
                st.session_state['parsed_pdf']['languages'] = autofilled_languages

            with st.expander(label="EXPERIENCE", expanded=True,):
                work_exp = st.session_state['parsed_pdf'].get('work_exp', [])
                autofilled_work_exp = deepcopy(work_exp)
                for i, we in enumerate(work_exp):
                    # company
                    autofilled_work_exp[i]["work_company"] = st.text_input(f"Company", 
                                                                    work_exp[i].get("work_company", ""), 
                                                                    key=f"work_company_{i}")

                    # timeline
                    c1, c2 = st.columns(2)
                    timeline = work_exp[i].get("work_timeline", [None,None])
                    if timeline is None: timeline = [None, None]
                    w_f = c1.text_input("From", timeline[0], 
                                        key=f"work_timeline_from_{i}")
                    w_t = c2.text_input("To", timeline[-1], 
                                        key=f"work_timeline_to_{i}")
                    autofilled_work_exp[i]["work_timeline"] = [w_f, w_t]

                    # title
                    autofilled_work_exp[i]["work_title"] = st.text_input(f"Title", 
                                                                    work_exp[i].get("work_title", ""), 
                                                                    key=f"work_title_{i}")

                    # description
                    autofilled_work_exp[i]["work_description"] = st.text_area(f"Description",
                                                                        work_exp[i].get("work_description", ""),
                                                                        height=150,
                                                                        key=f"work_description_{i}",)
                    bc1, bc2 = st.columns(2, gap="large")
                    bc1.button("✍️ Rewrite", on_click=write_description, args=(i,), key=f"rewrite_button_desc_{i}")
                    bc2.button("🔄 Reset", on_click=reset_description, args=(i,), key=f"reset_button_desc_{i}")  

                    # responsibilities
                    resps_list = work_exp[i].get("work_responsibilities", [])
                    height = min(100*len(resps_list) if len(resps_list) > 0 else 100, 300)
                    
                    resps_str = "\n".join([f"- {c}" for c in resps_list])
                    autofilled_work_exp[i]["work_responsibilities"] = st.text_area(f"Responsibilities",
                                                                            resps_str,
                                                                            height=height,
                                                                            key=f"work_responsibilities_{i}")

                    bc1, bc2 = st.columns(2, gap="large")
                    bc1.button("✍️ Rewrite", on_click=rewrite_resp, args=(i,), key=f"rewrite_button_resp_{i}")
                    bc2.button("🔄 Reset", on_click=reset_resp, args=(i,), key=f"reset_button_resp_{i}")            
                    
                    
                    # technologies
                    autofilled_work_exp[i]["work_technologies"] = st.text_area(f"Technologies",
                                                                        work_exp[i].get("technologies", ""),
                                                                        key=f"work_technologies_{i}")

                    st.markdown("""---""")

            with st.expander(label="EDUCATION", expanded=True,):
                edus = st.session_state['parsed_pdf'].get('education', [])
                autofilled_edus = deepcopy(edus)
                if len(edus) > 0:
                    for i, edu in enumerate(edus):
                        # Degree
                        autofilled_edus[i]["edu_degree"] = st.text_input(f"Degree",
                                                                    edus[i].get("edu_degree", ""),
                                                                    key=f"edu_degree_{i}")

                        # timeline
                        c1, c2 = st.columns(2)
                        edu_timeline = edus[i].get("edu_timeline", [None,None])
                        if len(edu_timeline) < 2:
                            edu_timeline = [None, None]
                        w_f = c1.text_input("From",
                                            edu_timeline[0], 
                                            key=f"edu_timeline_from_{i}")
                        w_t = c2.text_input("To", 
                                            edu_timeline[-1], 
                                            key=f"edu_timeline_to_{i}")
                        autofilled_edus[i]["edu_timeline"] = [w_f, w_t]
                        
                        # school
                        autofilled_edus[i]["edu_school"] = st.text_input(f"School", 
                                                                    edus[i].get("edu_school", ""), 
                                                                    key=f"edu_school_{i}")

                        # GPA
                        autofilled_edus[i]["edu_gpa"] = st.text_input(f"GPA", 
                                                                edus[i].get("edu_gpa", ""), 
                                                                key=f"edu_gpa_{i}")
                        
                        # description
                        autofilled_edus[i]["edu_description"] = st.text_area(f"Description",
                                                                        edus[i].get("edu_description", ""),
                                                                        height=100,
                                                                        key=f"edu_description_{i}",)
                        st.markdown("""---""")

            with st.expander(label="PROJECTS", expanded=True):
                projects = st.session_state['parsed_pdf'].get('projects', [])
                autofilled_projects = deepcopy(projects)
                if len(projects) > 0:
                    for i, prj in enumerate(projects):
                        # name
                        autofilled_projects[i]["project_name"] = st.text_input("Project name",
                                                                        projects[i].get("project_name", ""),
                                                                        key=f"project_name_{i}",)

                        # timeline
                        c1, c2 = st.columns(2)
                        timeline = projects[i].get("project_timeline", [None,None])
                        if timeline is None: timeline = [None,None]
                        w_f = c1.text_input("From", timeline[0], 
                                            key=f"project_timeline_from_{i}")
                        w_t = c2.text_input("To", timeline[-1], 
                                            key=f"project_timeline_to_{i}")
                        autofilled_projects[i]["project_timeline"] = [w_f, w_t]
                        
                        # description
                        autofilled_projects[i]["project_description"] = st.text_area(f"Description",
                                                                        projects[i].get("project_description", ""),
                                                                        height=100,
                                                                        key=f"project_description_{i}",)

                        # responsibilities
                        resps_list = projects[i].get("project_responsibilities", [])
                        height = min(100*len(resps_list) if len(resps_list) > 0 else 100, 300)
                        
                        resps_str = "\n".join([f"- {c}" for c in resps_list])
                        autofilled_projects[i]["project_responsibilities"] = st.text_area(f"Responsibilities",
                                                                                resps_str,
                                                                                height=height,
                                                                                key=f"project_responsibilities_{i}")
                        
                        # technologies
                        autofilled_projects[i]["project_technologies"] = st.text_area(f"Technologies",
                                                                            projects[i].get("project_technologies", ""),
                                                                            key=f"project_technologies_{i}")

            with st.expander(label="SKILLS", expanded=True,):
                certifications = st.session_state['parsed_pdf'].get('certifications', [])
                height = min(100*len(certifications) if len(certifications) > 0 else 100, 300)
                certifications = st.text_area("Certifications", "\n".join(certifications),
                                            height=height,
                                            key="certifications")

                skills = st.session_state['parsed_pdf'].get("skills", [])
                autofilled_skills = deepcopy(skills)
                c1, c2 = st.columns([4,1])
                for i,skill in enumerate(skills):
                    visibility = "visible" if i == 0 else "hidden"
                    skill_name = c1.text_input("Skill name", skills[i].get("skill_name", ""), 
                                                label_visibility=visibility, 
                                                key=f"skill_name_{i}")
                    
                    autofilled_skills[i] = {"skill_name": skill_name}

                # new skills
                offset = len(autofilled_skills)
                if 'new_skills' not in st.session_state:
                    st.session_state['new_skills'] = []
                if len(st.session_state['new_skills']) == 0:
                    st.button("Look for more skills", on_click=infer_more_skills)
                new_skills = st.session_state['new_skills']
                for i,skill in enumerate(new_skills):
                    visibility = "visible" if i == 0 else "hidden"
                    skill_name = c1.text_input("", new_skills[i].get("skill_name", ""), 
                                                label_visibility=visibility, 
                                                key=f"skill_name_{i+offset}")
                    autofilled_skills.append({"skill_name": skill_name})

            c1, c2 = st.columns(2, gap='large')
            c1.button("Submit", on_click=submit_form, key="submit")
            
            if st.session_state['output_json'] is not None:
                # download_data = json.dumps(st.session_state['output_json'])
                processed_data = post_process(st.session_state['output_json'])
                download_data = create_docx_file(processed_data)
                bio = io.BytesIO()
                download_data.save(bio)
                c2.download_button("🖨️ Export file", 
                                data=bio.getvalue(), 
                                file_name='export_resume.docx', 
                                mime="docx",
                                on_click=downloader_callback, key="export")
            # if st.session_state.get('output_json') is not None:
            #     #status_edit.update(label="Completed", state="complete", expanded=False)
            #     st.toast("You can export the resume now!", icon="🖨️")
        
        with tab_chat:

        # chat 
            if "qa_chain" in st.session_state and st.session_state.qa_chain is not None:
                
                st.markdown('<div class="floating-chat">', unsafe_allow_html=True)

                st.markdown("Ask anything about this CV!")

                # 1. Khởi tạo state
                if "messages" not in st.session_state:
                    st.session_state.messages = []

                # 2. Hiển thị lịch sử chat (user + assistant)
                for message in st.session_state.messages:
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])

                prompt = st.chat_input("What do you want to ask?")

                if prompt:
                    # Lưu user question
                    st.session_state.messages.append({"role": "user", "content": prompt})

                    # Lấy câu trả lời
                    with st.spinner("Thinking..."):
                        retriever = st.session_state.qa_chain.retriever

                        # 2. Gọi retriever một cách riêng biệt ĐỂ LẤY DOCS
                        retrieved_docs = retriever.get_relevant_documents(prompt)

                        # 3. BÂY GIỜ MỚI IN RA ĐỂ DEBUG
                        print("="*50)
                        print("CONTEXT RETRIEVED FOR THE LLM:")
                        for i, doc in enumerate(retrieved_docs):
                            print(f"--- Document {i+1} ---\n{doc.page_content}\n")
                        print("="*50)
                        
                        response = st.session_state.qa_chain({
                            "query": prompt,
                            "chat_history": [
                                (m["role"], m["content"]) 
                                for m in st.session_state.messages 
                                if m["role"] in ["user", "assistant"]
                            ]
                        })
                    
                        answer = response["result"]

                    # Lưu bot answer
                    st.session_state.messages.append({"role": "assistant", "content": answer})

                    # Rerun để input luôn ở cuối
                    st.rerun()
            else:
                st.info("📑 Please submit CV first to start chatting.")
            

                # Đóng thẻ div
            #st.markdown('</div>', unsafe_allow_html=True)

    
if st.session_state.page == 'Filter CVs':
    st.set_page_config(page_title="Filter CVs for HR", page_icon="🧑‍💼")
    st.title("🧑‍💼 Filter CVs for HR")

    with st.sidebar:
        jd_file = st.file_uploader("Upload job description (JD)", type=['pdf', 'docx'])
        uploaded_cvs = st.file_uploader(
            "Upload CVs that need filtering (PDF or DOCX)",
            type=['pdf', 'docx'],
            accept_multiple_files=True
        )

    # --- Khởi tạo session_state ---
    if "cv_parsed" not in st.session_state:
        st.session_state.cv_parsed = {}

    if uploaded_cvs:
        with st.expander("Uploaded CVs", expanded=True):
            st.subheader("Preview uploaded CVs")

            cv_filenames = [cv.name for cv in uploaded_cvs]

            # --- Extract toàn bộ CV ngay sau khi upload ---
            if "cv_parsed" not in st.session_state:
                st.session_state.cv_parsed = {}
            extracted_any = False
            for cv_file in uploaded_cvs:
                cv_name = cv_file.name
                if cv_name not in st.session_state.cv_parsed:
                    with st.spinner(f"Extracting {cv_name}..."):
                        file_bytes = cv_file.read()
                        cv_text = get_text_from_file(file_bytes, cv_file.name, file_role="cv")
                        cv_parsed = process_and_parse_cv(cv_text, cv_file.name)
                        st.session_state.cv_parsed[cv_name] = cv_parsed
                        cv_file.seek(0)  # reset con trỏ file sau khi đọc
                    extracted_any = True
            
            if extracted_any:
                st.toast("✅ All CVs extracted successfully!")

            # --- Chọn CV để xem và chỉnh sửa ---
            selected_cv_name = st.selectbox("Choose CV to preview:", options=cv_filenames)
            selected_cv_index = cv_filenames.index(selected_cv_name)
            selected_cv_file = uploaded_cvs[selected_cv_index]
            file_bytes = selected_cv_file.read()
            file_extension = selected_cv_file.name.split('.')[-1]

            with st.expander("CV Preview", expanded=True):
                display_file(file_bytes, file_extension)

            #with st.expander("Extracted CV Information", expanded=True):
            cv_parsed = st.session_state.cv_parsed[selected_cv_name]

        #     # --- Chuẩn hóa dữ liệu ---
            yoe_raw = cv_parsed.get("years_of_experience", 0)
            try:
                yoe = int(yoe_raw)
            except (ValueError, TypeError):
                yoe = 0

            skills_list = cv_parsed.get("skills", [])
            clean_skills = []
            for s in skills_list:
                if isinstance(s, dict):
                    clean_skills.append(
                        s.get("name")
                        or s.get("skill")
                        or s.get("skill_name")
                        or str(s)
                    )
                else:
                    clean_skills.append(str(s))

            education_list = cv_parsed.get("education", [])
            degree = ""
            if education_list and isinstance(education_list, list):
                first_edu = education_list[0]
                degree = first_edu.get("edu_degree", "")

            # --- Form chỉnh sửa ---
            # st.write("### Edit extracted data (optional)")
            # yoe = st.number_input("Years of Experience", min_value=0, value=yoe)
            # skills_str = st.text_area("Skills (comma-separated)", ", ".join(clean_skills))
            # degree = st.text_input("Highest Degree", degree)

            # # --- Chuẩn bị dữ liệu lưu ---
            # skills_cleaned = [s.strip() for s in skills_str.split(",") if s.strip()]

            save_data = cv_parsed
            if st.button("💾 Save All Extracted CVs"):
                output_dir = "output/extracted_json/cv"
                os.makedirs(output_dir, exist_ok=True)

                for cv_name, cv_parsed in st.session_state.cv_parsed.items():
                    # --- Chuẩn hóa dữ liệu giống như lúc lưu từng CV ---
                    yoe_raw = cv_parsed.get("years_of_experience", 0)
                    try:
                        yoe = int(yoe_raw)
                    except (ValueError, TypeError):
                        yoe = 0

                    skills_list = cv_parsed.get("skills", [])
                    clean_skills = []
                    for s in skills_list:
                        if isinstance(s, dict):
                            clean_skills.append(
                                s.get("name")
                                or s.get("skill")
                                or s.get("skill_name")
                                or str(s)
                            )
                        else:
                            clean_skills.append(str(s))

                    education_list = cv_parsed.get("education", [])
                    degree = ""
                    if education_list and isinstance(education_list, list):
                        first_edu = education_list[0]
                        degree = first_edu.get("edu_degree", "")
                    
                    save_data = cv_parsed

                    safe_name = re.sub(r'[^A-Za-z0-9_.-]', '_', cv_name)
                    save_path = os.path.join(output_dir, f"extracted_cv_{safe_name}.json")

                    with open(save_path, "w", encoding="utf-8") as f:
                        json.dump(save_data, f, ensure_ascii=False, indent=4)

                st.toast("✅ All extracted CVs have been saved successfully!")

# đảm bảo session storage cho jd_parsed
    if "jd_parsed" not in st.session_state:
        st.session_state.jd_parsed = {}
    if jd_file:
        with st.expander("Uploaded JD", expanded=True):
            st.subheader("Preview uploaded JD")

            # --- Preview file ---
            with st.expander("JD Preview", expanded=True):
                jd_file.seek(0)
                file_bytes = jd_file.read()
                print("JD file type:", getattr(jd_file, "type", "unknown"))
                file_extension = jd_file.name.split('.')[-1]
                display_file(file_bytes, file_extension)

            # --- Extraction (cached per filename in session_state) ---
            with st.expander("JD extraction", expanded=True):
                key = jd_file.name  # dùng tên file làm key trong session_state

                if key not in st.session_state.jd_parsed:
                    st.info("Extracting JD information...")
                    # Trích text + parse (chỉ chạy 1 lần cho file này)
                    jd_text = get_text_from_file(file_bytes, jd_file.name, file_role="jd")
                    jd_parsed = process_and_parse_jd(jd_text, jd_file.name)
                    print (jd_parsed)
                    st.session_state.jd_parsed[key] = jd_parsed
                else:
                    jd_parsed = st.session_state.jd_parsed[key]
                    #st.info("✅ Loaded parsed JD from session (no re-extraction)")

                # Nếu jd_parsed là None hoặc không phải dict -> fallback
                if not isinstance(jd_parsed, dict):
                    jd_parsed = {}
                    st.warning("Parsed JD is empty or invalid. You can fill the form manually.")

                # ----- Chuẩn hóa dữ liệu trước khi hiển thị form -----
                # experience
                exp_raw = jd_parsed.get("required_experience_years", 0)
                try:
                    required_experience_years_default = int(exp_raw)
                except (ValueError, TypeError):
                    required_experience_years_default = 0

                # education
                required_education_default = jd_parsed.get("required_education", "") or ""

                # skills (gộp hết về 1 danh sách duy nhất)
                skills_data = jd_parsed.get("skills", {})
                if isinstance(skills_data, dict):
                    all_skills = []
                    for k, v in skills_data.items():
                        if isinstance(v, list):
                            all_skills.extend(v)
                    skills_default = ", ".join(str(s) for s in all_skills)
                elif isinstance(skills_data, list):
                    skills_default = ", ".join(str(s) for s in skills_data)
                else:
                    skills_default = str(skills_data)

                # ----- Form chỉnh sửa -----
                st.markdown("### 📝 Review & Edit Extracted JD Information")

                with st.form("jd_edit_form"):
                    required_experience_years = st.number_input(
                        "Required Experience (Years)",
                        min_value=0,
                        value=required_experience_years_default
                    )

                    required_education = st.text_area(
                        "Required Education",
                        required_education_default
                    )

                    skills_input = st.text_area(
                        "Skills (comma-separated)",
                        skills_default
                    )

                    submitted = st.form_submit_button("💾 Save JD Info")

                    if submitted:
                        # xóa file JD từ lần up trước đó
                        
                        output_dir = "output/extracted_json/jd"
                        os.makedirs(output_dir, exist_ok=True) # Ensure directory exists
                        safe_name = re.sub(r'[^A-Za-z0-9_.-]', '_', key)
                        old_save_path = os.path.join(output_dir, f"jd_final_{safe_name}.json")
                        if os.path.exists(old_save_path):
                            try:
                                os.remove(old_save_path)
                                st.info(f"Removed old JD file: {old_save_path}")
                            except Exception as e:
                                st.warning(f"Could not remove old JD file {old_save_path}: {e}")
                        
                        jd_final = {
                            "required_experience_years": int(required_experience_years),
                            "required_education": required_education.strip(),
                            "skills": [s.strip() for s in skills_input.split(",") if s.strip()]
                        }

                        # update session_state
                        st.session_state.jd_parsed[key] = jd_final

                        # --- Ghi file JSON ---
                        output_dir = "output/extracted_json/jd"
                        os.makedirs(output_dir, exist_ok=True)
                        safe_name = re.sub(r'[^A-Za-z0-9_.-]', '_', key)
                        save_path = os.path.join(output_dir, f"jd_final_{safe_name}.json")

                        with open(save_path, "w", encoding="utf-8") as f:
                            json.dump(jd_final, f, ensure_ascii=False, indent=4)

                        st.toast("✅ JD information saved successfully!")
                        #st.info(f"Saved to {save_path}")
                    #xóa file cũ khi chạy lại 
                    # --- Nút lưu toàn bộ CV ---

    # 3. Nút bấm để bắt đầu quá trình lọc
    if st.button("Start Filtering CVs"):
        if not jd_file:
            st.warning("Please upload at least one job description.")
        elif not uploaded_cvs:
            st.warning("Please upload at least one CV.")
        else:
            with st.spinner("Analyzing and ranking CVs..."):
                results = rank_with_bm25_and_sbert()
                st.toast("Done ranking CVs!")

                for jd_name, data in results.items():
                    #st.markdown(f"## 🧾 JD: `{jd_name}`")

                    # === BM25 Results ===
                    # st.markdown("### 🔍 Top CVs (BM25)")
                    # for i, (cv_name, score) in enumerate(data["bm25"], 1):
                    #     st.write(f"{i}. **{cv_name}** — BM25 score: `{score:.3f}`")

                    # # === SBERT Results ===
                    # st.markdown("### 💡 Top CVs (SBERT Reranking)")
                    # for i, (cv_name, score) in enumerate(data["sbert"], 1):
                    #     st.write(f"{i}. **{cv_name}** — Cosine similarity: `{score:.4f}`")

                    # === Cohere Results ===
                    st.markdown("### Top 3 CVs")
                    for i, (cv_name, score) in enumerate(data["cohere"], 1):
                        st.write(f"{i}. **{cv_name}** — Relevance score: `{score:.4f}`")

                    st.markdown("---")






#skill nào khớp --> debug kĩ
#chỉnh trọng số điểm 