import json
import pandas as pd
import os
from openai import AsyncOpenAI
from dotenv import load_dotenv
import asyncio

load_dotenv()

def generate_prompt(property_description, ui_element_identifier):
    template = """
You are an expert in Python programming and Android app testing, and your role is to write test snippets for Android apps.

The following APIs are available for test writing:
ui_element: self.device(identifier)
click: ui_element.click()
long click: ui_element.long_click()
rotate device to left: self.device.set_orientation("left")
rotate device to natural: self.device.set_orientation("natural")
back: self.device.press("back")
recent: self.device.press("recent")
edit: ui_element.set_text(text)
exists: ui_element.exists()
count: ui_element.count
get text: ui_element.get_text()
selected: ui_element.info["selected"]
checked: ui_element.info["checked"]
scroll the screen to ui element: self.device(scrollable=True).scroll.to(identifier), return true if found, otherwise false
srcoll horizontal: ui_element.scroll.horiz.forward(steps=100)
scroll to right: self.device.swipe_ext("right")  
scroll down to the end: self.device(scrollable=True).scroll.toEnd(steps=100)
relative positioning: 
selects B on the left side of A: A.left(B's identifier)
selects B on the right side of A: A.right(B's identifier)
selects B above A: A.up(B's identifier),
selects B under A: A.down(B's identifier)
children:
selects A's child B: A.child(B's identifier)
siblings:
selects A's sibling B: A.sibling(B's identifier)
send search action to the device: self.device.send_action("search")
open keyboard: self.device.set_fastinput_ime(False)
close keyboard: self.device.set_fastinput_ime(True)
done: self.device(resourceId="com.google.android.inputmethod.latin:id/key_pos_ime_action")
text contains string s: self.device(textContains=s)
text equals string s: self.device(text=s)
open notification: self.device.open_notification()
Next button on the notification: self.device(description="Next")
get the current time from the device: self.device(resourceId="com.android.systemui:id/clock").get_text()

The app's UI element identifiers are detailed below for reference, ensuring accurate element selection in tests.
{ui_element_identifier}

Here is an example test snippet that you might write, based on a given property description:

Example 1: 

Property description:
Precondition: text "Edit Tags" exists and search button exists
Function body:
1. randomly select a tag
2. get the text of the selected tag as tag name
3. click the delete button on the right of the selected tag
4. assert the selected tag name not exists

Property test snippet:
    @precondition(lambda self: self.device(text="Edit Tags").exists() and self.device(resourceId="com.automattic.simplenote:id/menu_search").exists())
    @rule()
    def delete_tag(self):
        tag_count = self.device(resourceId="com.automattic.simplenote:id/tag_name").count
        selected_tag_index = random.randint(0, tag_count - 1)
        selected_tag = self.device(resourceId="com.automattic.simplenote:id/tag_name")[selected_tag_index]
        selected_tag_name = selected_tag.get_text()
        selected_tag.right(resourceId="com.automattic.simplenote:id/tag_trash").click()
        assert not self.device(text="selected_tag_name").exists()

Example 2: 

Property description:
Precondition: text "All Notes" exists and fab button exists
Function body:
1. randomly select a note content
2. get the text of the note content
3. select the note title above the selected note content
4. get the text of the selected note title
5. click the note title
6. click the options button
7. click back
8. assert the text of note content exists and the text of note title exists

Property test snippet:
@precondition(lambda self: self.device(text="All Notes").exists() and self.device(resourceId="com.automattic.simplenote:id/fab_button").exists())
    @rule()
    def note_title_and_content(self):
        note_content = random.choice(self.device(resourceId="com.automattic.simplenote:id/note_content"))
        note_content_text = note_content.get_text()
        note_title = note_content.up(resourceId="com.automattic.simplenote:id/note_title")
        note_title_text = note_title.get_text()
        note_title.click()
        self.device(description="More options").click()
        self.device.press("back")
        assert self.device(text=note_content_text).exists() and self.device(text=note_title_text).exists()

Your task:
Using the available APIs, UI element identifiers and following the example format, please write a test snippet for the following property:
{property_description}

Respond only with the Python code snippet, strictly adhering to the given property description. Do not include any explanations, comments, or text outside the code block.
    """
    return template.replace("{property_description}", property_description).replace(
        "{ui_element_identifier}", ui_element_identifier
    )

async def call_llm(prompt,llm="gpt-4o"):
    try:
        client = None
        model = None
        if llm == "deepseek_fireworks":
            print("calling deepseek")
            client = AsyncOpenAI(api_key=os.environ.get("DEEPSEEK_API_KEY"),base_url=os.environ.get("DEEPSEEK_URL"))
            model = os.environ.get("DEEPSEEK_MODEL")
        else:
            client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            model="gpt-4o"
            print("calling gpt-4o")
        completion = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0,
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Error: {e}")
        return ""


async def process_column(df, col_name):
    
    tasks = []

    for index, description in enumerate(df[col_name]):
        ui_identifier_path = df.iloc[index, 1]  # get UI Element Identifier
        try:
            with open(ui_identifier_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            ui_identifier = json.dumps(config, ensure_ascii=False)
        except Exception as e:
            print(f"read {ui_identifier_path} error: {e}")
            ui_identifier = ""
            
        prompt = generate_prompt(description, ui_identifier)
        tasks.append(call_llm(prompt))

    processed_results = await asyncio.gather(*tasks)
    empty_result = ["" for _ in processed_results]

    # save the results on the next column
    new_col_name = f"{col_name}_Processed"
    empty_col_name = f"{col_name}_correct"
    df.insert(df.columns.get_loc(col_name) + 1, new_col_name, processed_results)
    df.insert(df.columns.get_loc(col_name) + 2, empty_col_name, empty_result)


async def main(input_file, output_file):
    try:
        df = pd.read_excel(input_file)
        property_description_cols = list(df.columns[2:])

        await asyncio.gather(
            *(process_column(df, col_name) for col_name in property_description_cols)
        )

        # save the result to the output
        df.to_excel(output_file, index=False)
        print(f"Results saved to {output_file}")
    except Exception as e:
        print(f"Error: {e}")

# put the widget widget identifier and the property description in the file property.xlsx
file_path = "property.xlsx"
output_file = "generated_executable_property.xlsx"
asyncio.run(main(file_path, output_file))
