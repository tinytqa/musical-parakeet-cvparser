import json

jd_template = """
Field                  Description                                          Key name                      Format
Required Experience    Minimum number of years of experience required.     required_experience_years      int or string
Required Education     The minimum required degree or educational level.  required_education             string
Skills                 Skills required for the job (with importance).     skills                         dict of {skill: importance_score (1–5)}
"""

jd_example = """
{
  "required_experience_years": 2,
  "required_education": "Bachelor’s degree in Computer Science or related field",
  "skills": {
    "Python": 5,
    "Machine Learning": 5,
    "Deep Learning": 4,
    "TensorFlow": 4,
    "Data Analysis": 3,
    "Communication": 2
  }
}
"""

def prompt_to_parse_jd(jd_text):
    """
    Sinh prompt yêu cầu LLM trích xuất thông tin chính (năm kinh nghiệm, kỹ năng có trọng số, bằng cấp)
    từ một đoạn Job Description (JD).
    """

    prompt = f"""
    job_description:
    <begin>
    {jd_text}
    <end>

    example:
    <begin>
    {jd_example}
    <end>

    template:
    <begin>
    {jd_template}
    <end>

    You are an expert AI assistant specialized in HR data extraction.
    Your task is to extract ONLY the key structured information from the provided job description.

    Follow these strict extraction rules:

    1.  Regarding "required_experience_years":
        * The output value MUST be an **Integer**.
        * Follow the same rules as before (0 for "<1 year", min value for ranges, etc).

    2.  Regarding "required_education":
        * Extract the HIGHEST degree requirement or field of study mentioned.
        * If not mentioned, return null.

    3.  Regarding "skills":
        * Extract ALL explicitly mentioned skills (both technical and soft skills).
        * Each skill must have an **importance score** between 1–5.
        * Importance scoring rules:
            - If the JD uses words like **"must have"**, **"required"**, **"essential"**, or **"strong command of"**, assign **5**.
            - If it uses words like **"preferred"**, **"good to have"**, or **"nice to have"**, assign **3**.
            - If the JD just lists the skill without emphasis, assign **3**.
            - If it’s only slightly mentioned or optional, assign **2**.
            - If unsure, default to 3.
        * Example output format:
            "skills": {{
                "Python": 5,
                "SQL": 4,
                "Excel": 2
            }}

    4.  Output format:
        * Output must be a single valid JSON object matching the template.
        * No explanations, no markdown formatting, only pure JSON.

    <output json>
    """

    return prompt

def post_parse_jd(output): # lọc ra json từ kết quả trả về của AI
  
    try:
        start = output.find('{')
        end = output.rfind('}') + 1
        json_str = output[start:end]

        # Chuyển chuỗi JSON thành dict
        return json.loads(json_str)
    
    except json.JSONDecodeError:
        return {"raw_text": output}