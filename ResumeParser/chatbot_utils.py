import os
import shutil

import fitz
from rag import build_rag_pipeline
import streamlit as st

def to_txt(export, output_dir):
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
            # Chứng chỉ
            if export.get("certifications"):
                f.write("## Certifications\n")
                for cert in export["certifications"]:
                    f.write(f"- {cert}\n")
                f.write("\n")
            # Kỹ năng
            if export.get("skills"):
                f.write("## Skills\n")
                skill_names = [skill.get('skill_name', '') for skill in export['skills']]
                f.write(", ".join(skill_names) + "\n")
                f.write("\n")
        return txt_path

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
    return export

# ===== Tạo folder output =====
def save_and_prepare_chatbot(export):
    export = submit_form()
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
        st.json.dump(export, f, ensure_ascii=False, indent=4)

    # ==== Tạo file TXT =====
    txt_path = to_txt(export, output_dir)
    
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

    return cv_text_content, output_dir

def build_chatbot_pipeline(cv_text_content, output_dir):
    # 2. Gọi hàm build_rag_pipeline từ rag.py
    # Truyền thêm output_dir để lưu các file chunk (nếu muốn)
    export = submit_form()
    cv_text_content, output_dir = save_and_prepare_chatbot(export)
    qa_chain = build_rag_pipeline(cv_text_content, output_dir)
    
    # 3. Lưu pipeline vào session_state để giao diện sử dụng
    st.session_state.qa_chain = qa_chain
    
    # 4. Khởi tạo hoặc xóa lịch sử chat cũ
    st.session_state.messages = []
    
    if qa_chain:
        st.toast("Chatbot is ready!", icon="✅")
    else:
        st.toast("Failed to initialize chatbot.", icon="❌")    
    
    return qa_chain