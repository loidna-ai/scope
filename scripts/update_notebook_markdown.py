import json
import os

notebook_path = r"c:/Users/user/Documents/Project/P_04_Scope/notebook/Agent_1_Contact_Expert.ipynb"

def update_notebook():
    if not os.path.exists(notebook_path):
        print(f"Error: Notebook not found at {notebook_path}")
        return

    with open(notebook_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Modify the first cell (Markdown)
    if data['cells'] and data['cells'][0]['cell_type'] == 'markdown':
        source = data['cells'][0]['source']
        
        # Check if already updated to avoid duplication
        joined_source = "".join(source)
        if "Dual Image Analysis" in joined_source:
            print("Notebook already contains Dual Image Analysis description.")
            return

        # Append new description
        new_content = [
            "\n",
            "### \u2728 Dual Image Analysis (New)\n",
            "\n",
            "**Specialist** 및 **Classifier** 단계에서 **원본 이미지(Context)**와 **Crop 이미지(Detail)**를 동시에 입력받아 분석합니다.\n",
            "- **Context**: 전체적인 화재 패턴과 주변 장치와의 연결성을 파악합니다.\n",
            "- **Detail**: 초해상도(Super Resolution) 확대된 ROI를 통해 미세한 용융 흔적을 식별합니다.\n",
            "이 두 가지 시각 정보를 결합하여 단일 크롭 이미지 분석 시 발생할 수 있는 오판(단순 탄화를 용융으로 오인 등)을 방지합니다."
        ]
        
        source.extend(new_content)
        data['cells'][0]['source'] = source
        print("Updated markdown cell with Dual Image Analysis description.")

        with open(notebook_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1)
        print("Notebook saved successfully.")
    else:
        print("First cell is not markdown or empty.")

if __name__ == "__main__":
    update_notebook()
