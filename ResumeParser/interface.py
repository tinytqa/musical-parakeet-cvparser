from copy import deepcopy
import io
import json
import os
import shutil
from docx import Document
import fitz
import streamlit as st
import re
from export_resume import create_docx_file, post_process
from prompt import post_add_skills, post_rewrite_task, post_write_description, prompt_to_add_skills, prompt_to_rewrite_task, prompt_to_write_description
from text_extraction import extract_text_from_file
from llm_utils import call_gemini

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



def display_file(file_bytes: bytes, file_type: str):
    """
    Chỉ hiển thị file PDF hoặc DOCX trong Streamlit (preview),
    không lưu vào thư mục output.
    """
    if file_type.lower() == 'pdf':
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        image_list = []
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")  # chỉ giữ ảnh trong memory
            image_list.append(img_bytes)
        doc.close()
        st.image(image_list)

    elif file_type.lower() == 'docx':
        doc = Document(io.BytesIO(file_bytes))
        parts = []

        for para in doc.paragraphs:
            text_content = para.text.strip()
            if not text_content:
                continue

            style = para.style.name if para.style else ""
            if style.startswith("Heading"):
                level = style.replace("Heading", "").strip()
                level = int(level) if level.isdigit() else 1
                parts.append(f"{'#' * level} {text_content}")
            elif "List Bullet" in style or "List Number" in style:
                parts.append(f"- {text_content}")
            else:
                parts.append(text_content)

        for table in doc.tables:
            for row in table.rows:
                row_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if row_text:
                    parts.append(" | ".join(row_text))

        formatted_text = "\n".join(parts)
        st.markdown(formatted_text)

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

# def submit_form(): # lấy dữ liệu đã được AI xử lý --> lưu ra file json hoàn chỉnh (bản json final)
#     export_work_exp = []
#     for i in range(len(autofilled_work_exp)):
#         ewe = {
#             "work_timeline": [st.session_state[f"work_timeline_from_{i}"], st.session_state[f"work_timeline_to_{i}"]],
#             "work_company": st.session_state[f"work_company_{i}"],
#             "work_title": st.session_state[f"work_title_{i}"],
#             "work_description": st.session_state[f"work_description_{i}"],
#             "work_responsibilities": [c[2:] for c in st.session_state[f"work_responsibilities_{i}"].split('\n')],
#             "work_technologies": st.session_state[f"work_technologies_{i}"]
#         }
#         export_work_exp.append(ewe)
    
#     export_education = []
#     for i in range(len(autofilled_edus)):
#         ee = {
#             "edu_timeline": [st.session_state[f"edu_timeline_from_{i}"], st.session_state[f"edu_timeline_to_{i}"]],
#             "edu_school": st.session_state[f"edu_school_{i}"],
#             "edu_degree": st.session_state[f"edu_degree_{i}"],
#             "edu_gpa": st.session_state[f"edu_gpa_{i}"],
#             "edu_description": st.session_state[f"edu_description_{i}"],
#         }
#         export_education.append(ee)
    
#     export_projects = []
#     for i in range(len(autofilled_projects)):
#         ep = {
#             "project_timeline": [st.session_state[f"project_timeline_from_{i}"], st.session_state[f"project_timeline_to_{i}"]],
#             "project_name": st.session_state[f"project_name_{i}"],
#             "project_description": st.session_state[f"project_description_{i}"],
#             "project_responsibilities": [c[2:] for c in st.session_state[f"project_responsibilities_{i}"].split('\n')],
#             "project_technologies": st.session_state[f"project_technologies_{i}"]
#         }
#         export_projects.append(ep)
    
#     export_skills = []
#     for i in range(len(autofilled_skills)):
#         es = {
#             "skill_name": st.session_state[f"skill_name_{i}"],
#         }
#         export_skills.append(es)
#     for i in range(len(autofilled_skills)):
#         es = {
#             "skill_name": st.session_state[f"skill_name_{i}"],
#         }
#         export_skills.append(es)

#     export_languages = []
#     for i in range(len(autofilled_languages)):
#         el = {
#             "lang": st.session_state[f"lang_{i}"],
#             "lang_lvl": st.session_state[f"lang_lvl_{i}"],
#         }
#         export_languages.append(el)    

#     export = {
#         "candidate_name": st.session_state.candidate_name,
#         "candidate_title": st.session_state.candidate_title,
#         "summary": st.session_state.summary,
#         "links": st.session_state.links.split('\n'),
#         "languages": export_languages,
#         "work_exp": export_work_exp,
#         "education": export_education,
#         "projects": export_projects,
#         "certifications": st.session_state.certifications.split('\n'),
#         "skills": export_skills
#     }

#     # Lưu vào session
#     st.session_state['output_json'] = export

#     candidate_name = export["candidate_name"].replace(" ", "_") or "unknown"

#     output_dir = os.path.join("output", f"cv_{candidate_name}")
#     if os.path.exists(output_dir):
#         try:
#             shutil.rmtree(output_dir)  # xóa cả thư mục cũ
#         except PermissionError:
#             st.warning(f"Không thể xóa folder cũ: {output_dir}, có thể đang mở ở nơi khác!")

#     os.makedirs(output_dir, exist_ok=True)

#     # Tạo folder riêng cho từng ứng viên
#     output_dir = os.path.join("output", f"cv_{candidate_name}")
#     os.makedirs(output_dir, exist_ok=True)
    
#     # Lưu JSON
#     with open(os.path.join(output_dir, "export_resume.json"), "w", encoding="utf-8") as f:
#         json.dump(export, f, ensure_ascii=False, indent=4)

#     # Lưu TXT (phiên bản text đơn giản)
#     txt_path = os.path.join(output_dir, "export_resume.txt")
#     with open(txt_path, "w", encoding="utf-8") as f:
#         f.write(f"Name: {export['candidate_name']}\n")
#         f.write(f"Title: {export['candidate_title']}\n\n")
#         f.write("Summary:\n" + export["summary"] + "\n\n")
        
#         f.write("Links:\n" + "\n".join(export["links"]) + "\n\n")
        
#         f.write("Languages:\n")
#         for lang in export["languages"]:
#             f.write(f"- {lang['lang']} ({lang['lang_lvl']})\n")
#         f.write("\n")

#         f.write("Work Experience:\n")
#         for we in export["work_exp"]:
#             f.write(f"- {we}\n")
#         f.write("\n")

#         f.write("Education:\n")
#         for edu in export["education"]:
#             f.write(f"- {edu}\n")
#         f.write("\n")

#         f.write("Projects:\n")
#         for proj in export["projects"]:
#             f.write(f"- {proj}\n")
#         f.write("\n")

#         f.write("Certifications:\n" + "\n".join(export["certifications"]) + "\n\n")
#         f.write("Skills:\n")

#         for skill in export["skills"]:
#             if isinstance(skill, dict):
#                 # nếu skill lưu dạng dict
#                 skill_name = skill.get("skill_name")
#                 f.write(f"- {skill_name}\n")


#     st.toast("Form submitted and files saved!", icon="🎯")

def submit_form(uploaded_file_bytes=None, uploaded_file_type=None):
    """
    Lấy dữ liệu từ session --> lưu ra JSON + TXT + ảnh (nếu có)
    """
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

    # ===== Tạo folder output =====
    candidate_name = export["candidate_name"].replace(" ", "_") or "unknown"
    output_dir = os.path.join("output", f"cv_{candidate_name}")

    if os.path.exists(output_dir):
        try:
            shutil.rmtree(output_dir)
        except PermissionError:
            st.warning(f"Không thể xóa folder cũ: {output_dir}, có thể đang mở ở nơi khác!")

    os.makedirs(output_dir, exist_ok=True)

    # ===== Lưu JSON =====
    with open(os.path.join(output_dir, "export_resume.json"), "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=4)

    # ===== Lưu TXT đơn giản =====
    txt_path = os.path.join(output_dir, "export_resume.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"Name: {export['candidate_name']}\n")
        f.write(f"Title: {export['candidate_title']}\n\n")
        f.write("Summary:\n" + export["summary"] + "\n\n")

        f.write("Links:\n" + "\n".join(export["links"]) + "\n\n")

        f.write("Languages:\n")
        for lang in export["languages"]:
            f.write(f"- {lang['lang']} ({lang['lang_lvl']})\n")
        f.write("\n")

        f.write("Work Experience:\n")
        for we in export["work_exp"]:
            f.write(f"- {we}\n")
        f.write("\n")

        f.write("Education:\n")
        for edu in export["education"]:
            f.write(f"- {edu}\n")
        f.write("\n")

        f.write("Projects:\n")
        for proj in export["projects"]:
            f.write(f"- {proj}\n")
        f.write("\n")

        f.write("Certifications:\n" + "\n".join(export["certifications"]) + "\n\n")

        f.write("Skills:\n")
        for skill in export["skills"]:
            if isinstance(skill, dict):
                f.write(f"- {skill.get('skill_name')}\n")

    # ===== Nếu file gốc là PDF thì lưu thêm ảnh từng trang =====
    if uploaded_file_bytes and uploaded_file_type and uploaded_file_type.lower() == "pdf":
        doc = fitz.open(stream=uploaded_file_bytes, filetype="pdf")
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=200)
            img_path = os.path.join(output_dir, f"page_{i+1}.png")
            pix.save(img_path)
        doc.close()

    st.toast("Form submitted and files saved!", icon="🎯")

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

def init_state(key, value):
    if key not in st.session_state:
        st.session_state[key] = value

init_state('parsed_pdf', dict())
init_state('uploaded', False)
init_state('processed', False)
init_state('output_json', None)

st.set_page_config(page_title="Resume Parser", page_icon="📑")
st.title("📑 Resume Parser",)

# Inject custom CSS to set the width of the sidebar
st.markdown(
    """
    <style>
        section[data-testid="stSidebar"] {
            width: 100% !important; # Set the width to your desired value
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# st.button("Restart", on_click="restart")
with st.sidebar:
    uploaded_file = st.file_uploader("Upload file PDF hoặc DOCX", on_change=uploader_callback)

    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        if uploaded_file.name.lower().endswith(".pdf"):
            display_file(file_bytes, 'pdf')
        elif uploaded_file.name.lower().endswith(".docx"):
            display_file(file_bytes, 'docx')
        else:
            st.warning("Chỉ hỗ trợ PDF và DOCX")
    else:
        st.info("Please upload file.")



# Xử lý trạng thái
# if st.session_state['processed']:
#     status = st.status("Editing the resume ... ", expanded=True)
# elif uploaded_file is not None:
#     status = st.status("Processing the resume ... ", expanded=True) 

# if uploaded_file is not None and not st.session_state.get('processed', False):
#     # Vì uploaded_file.read() đã dùng ở trên, cần reset pointer
#     uploaded_file.seek(0)
#     file_bytes = uploaded_file.read()
#     filename = uploaded_file.name

#     # Gọi hàm trích xuất text
#     status.write("👩‍💻 Analyzing the resume ...")
#     parsed_data = extract_text_from_file(file_bytes, filename)

#     # Đánh dấu đã xử lý xong
#     st.session_state['parsed_pdf'] = parsed_data
#     st.session_state['processed'] = True
#     status.update(label="Completed", state="complete", expanded=False)


if uploaded_file is not None and not st.session_state.get('processed', False):
    # Trạng thái: đang xử lý
    status_process = st.status("Processing the resume ...", expanded=True)
    uploaded_file.seek(0)
    file_bytes = uploaded_file.read()
    filename = uploaded_file.name

    status_process.write("👩‍💻 Analyzing the resume ...")
    parsed_data = extract_text_from_file(file_bytes, filename)

    st.session_state['parsed_pdf'] = parsed_data
    st.session_state['processed'] = True
    status_process.update(label="Completed", state="complete", expanded=False)

# Nếu đã xử lý xong thì hiển thị form nhập liệu
if st.session_state.get('processed', False):
    status_edit = st.status("✍️ Editing the resume ...", expanded=True)
    with st.expander(label="INFORMATION", expanded=True):
        st.markdown("""---""")

        # Lấy data từ session_state
        parsed_data = st.session_state.get("parsed_pdf", {})

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
            autofilled_work_exp[i]["technologies"] = st.text_area(f"Technologies",
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

    with st.expander(label="PROJECTS", expanded=True,):
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
    if st.session_state.get('output_json') is not None:
        status_edit.update(label="Completed", state="complete", expanded=False)