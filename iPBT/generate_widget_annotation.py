import asyncio
import glob
import io
from multiprocessing.util import debug
from openai import AsyncOpenAI, OpenAI
import base64
import json
from PIL import Image, ImageDraw
from dotenv import load_dotenv
import os

from openai import RateLimitError
load_dotenv()
from asyncio import Condition

class RateLimiter:
    def __init__(self):
        self.condition = Condition()
        self.is_active = False
        self.cooldown = 60  


rate_limiter = RateLimiter()
client = None
semaphore = None

def encode_image(image_path,bounds, save_path=None):
    """
    annotate the widget in the screenshot
    s"""
    with Image.open(image_path) as img:
        draw = ImageDraw.Draw(img)
        # view bound should be in original image bound
        draw.rectangle([min((img.width - 1), bounds[0]), min((img.height - 1), bounds[1]),
                        min((img.width), bounds[2]), min((img.height), bounds[3])], outline="red", width=5)

        if debug:
            save_path = f"./annotated_image/annotated_{os.path.basename(image_path)}"
        if save_path:
            img.save(save_path, "PNG")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

def crop_element(image_path, bounds, save_path=None):
    """
    crop the screenshot by bounds of widgets
    bounds format: [x1, y1, x2, y2]
    """
    try:
        img = Image.open(image_path)
        crop = img.crop(bounds)
        if debug:
            save_path = f"./cropped_image/cropped_element_{os.path.basename(image_path)}_{bounds[0]}_{bounds[1]}_{bounds[2]}_{bounds[3]}.png"
        if save_path:
            crop.save(save_path,"PNG")
        return crop
    except Exception as e:
        print(f"Error cropping image: {e}")
        return None
    
def encode_element_crop(image_path, bounds):
    """crop the widget"""

    crop_img = crop_element(image_path, bounds)

    buf = io.BytesIO()
    crop_img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def generate_final_widget_annotation(input_file):
    widgets_data = json.load(open(input_file, "r", encoding="utf-8"))
    final_output = {}
    for activity, widgets in widgets_data.items():
        final_output[activity] = []
        for widget in widgets:
            
            final_widget = {
                "text": widget.get("text", ""),
                "resource_id": widget.get("resource_id", ""),
                "description": widget.get("content_description", ""),
                "class": widget.get("class", ""),
                "semantic_label": widget.get("semantic_label", ""),
                "functionality": widget.get("functionality", "")
            }
            final_output[activity].append(final_widget)
    
    output_file = input_file.replace(".json", "_final.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)
    print(f"Final annotations saved to {output_file}")
        
async def generate_with_rate_limit(page_image_path, app_name, activity_name, widget, retries=5):
    global rate_limit_active
    
    for attempt in range(retries):
        # wait until no limit
        async with rate_limiter.condition:
            while rate_limiter.is_active:
                await rate_limiter.condition.wait()
        
        async with semaphore:
            try:
                result = await generate_single_widget_annotation(page_image_path, app_name, activity_name, widget)
                if result is None:
                    print(f" Attempt {attempt + 1}: Result is None, retrying...")
                    continue
                return result
                
            except RateLimitError as e:
                print(f" Attempt {attempt + 1}: Rate limit error: {e}")
                
                async with rate_limiter.condition:
                    if not rate_limiter.is_active:
                        
                        rate_limiter.is_active = True
                        print(f" Rate limit detected, pausing all tasks for {rate_limiter.cooldown}s...")
                        rate_limiter.condition.notify_all()     
                await asyncio.sleep(rate_limiter.cooldown)
                 
                async with rate_limiter.condition:
                    rate_limiter.is_active = False
                    print(" Rate limit cooldown complete, resuming tasks...")
                    rate_limiter.condition.notify_all()   
                continue
                
            except Exception as e:
                print(f" Attempt {attempt + 1}: Other error: {e}")
                await asyncio.sleep(2)
                continue
                
    print(" Exceeded max retries, giving up.")
    return None


async def generate_single_widget_annotation(page_image_path, app_name, activity_name, widget):
    """
    generate annotation for single widget
    """
    global client
    
    
    if client is None:
        client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    try:
        page_image = encode_image(page_image_path, widget["bounds"])
    except Exception as e:
        print(f"Widget bounds: {widget['bounds']}")
        print(f"Error encoding page image: {e}")
        return None

    if debug:
        print(type(widget["bounds"]))
    
    try:
        widget_image = encode_element_crop(page_image_path, widget["bounds"])
    except Exception as e:
        print(f"Error cropping widget image: {e}")
        return None
    if widget_image is None:
        print(f"Failed to crop widget image for bounds: {widget['bounds']}")
        return None

    # ===== construct prompt =====
    messages = [
    {
    "role": "system",
    "content": """You are a professional mobile app UI semantic annotation assistant. 
    Please annotate the provided UI widget with the semantic label and functionality based on the given context. 
    - The full page screenshot, where the target widget is highlighted with a red bounding box.
    - The cropped widget image and its attributes.
    - The provided app name and foreground activity name.

    Strict rules:
    1. You must ONLY annotate the SINGLE widget provided in the input.
    2. It is STRICTLY FORBIDDEN to invent or add any other widgets.
    3. You must output EXACTLY one JSON object for the given widget, with no explanations or extra text.
    4. The JSON object MUST contain ONLY these two fields:
    - semantic_label: a concise semantic description of the widget.
    - functionality: a brief description of the widget's functionality.

    Example:
    App name: "bankapp"
    Foreground Activity name: "MainActivity"

    Input widget:
    {
        "text": "Login",
        "resource_id": "btn_login",
        "content_description": "",
        "class": "android.widget.Button",
        "bounds": [50, 600, 200, 650]
    }

    Expected output:
    {
        "semantic_label": "Login button",
        "functionality": "Authenticate user and enter the app",
    }
    """
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"App name: {app_name}"},
                {"type": "text", "text": f"Foreground activity: {activity_name}"},
                {"type": "text", "text": "Here is the full page screenshot:"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{page_image}"}},
                {"type": "text", "text": "Target UI widget information:"},
                {"type": "text", "text": json.dumps(widget, ensure_ascii=False)},
                {"type": "text", "text": "Target UI widget (with cropped region):"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{widget_image}"}}
            ]
        }
    ]

    # ===== call GPT-4o mini =====
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            response_format={"type": "json_object"}
        )
        output = response.choices[0].message.content
        output = json.loads(output)  
    except RateLimitError as e:
        raise e
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        return None
    
    # ensure the output is formatted
    if not isinstance(output, dict) or "semantic_label" not in output or "functionality" not in output:
        print("Output format error, expected a JSON object with 'semantic_label' and 'functionality'.")
        return None
    
    widget["semantic_label"] = output["semantic_label"]
    widget["functionality"] = output["functionality"]
    
    widget.pop("screen_tag", None)
    return widget

async def generate_widget_annotations(app_name, state_dir_path, widgets_file_path):
    """
    generate functionality annotations for each widget
    """
    global semaphore, rate_limit_lock, resume_event
    
   
    semaphore = asyncio.Semaphore(20)
    
    
    output = {}
    widgets_file = json.load(open(widgets_file_path, "r", encoding="utf-8"))

    for activity_name, activity_widgets in widgets_file.items():
        tasks = []
        print(f"Processing activity: {activity_name}")
        for widget in activity_widgets:
            
            page_image_path = state_dir_path+"screen_"+widget["screen_tag"]+".png"
            if not os.path.exists(page_image_path):
                print(f"Page image {page_image_path} does not exist, skipping widget {widget}")
                continue
            tasks.append(generate_with_rate_limit(page_image_path, app_name, activity_name, widget))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for widget, result in zip(activity_widgets, results):
            if isinstance(result, Exception):
                print(f"Widget result: Exception - {result}")
                widget["error"] = "error: exception"
                output.setdefault(activity_name, []).append(widget)
            elif result is None:
                widget["error"] = "error: result is None"
                output.setdefault(activity_name, []).append(widget)
            else:
                output.setdefault(activity_name, []).append(result)

    return output

def load_all_json_file(path):
   
    json_files = glob.glob(path + "*.json")
    all_data = []

    for json_file in json_files:
        with open(json_file, "r", encoding="utf-8") as file:
            try:
                data = json.load(file)
                all_data.append(data)  
            except json.JSONDecodeError as e:
                print(f"read {json_file} error: {e}")

    return all_data


def get_widget_info(all_data, app_package,output_file):
    output = {}
    total_widgets = 0  
    for data in all_data:
        for view in data["views"]:
            if app_package in view["package"]:
                activity = data["foreground_activity"].split(".")[-1]
                if activity not in output.keys():
                    output[activity] = []
                
                if view['child_count'] > 0:
                    continue
                
                if view["text"] is None and view["resource_id"] is None and view["content_description"] is None:
                    continue
                widget = {
                    "screen_tag": data["tag"],
                    "text": view["text"] if view["text"] is not None else "",
                    "resource_id": view["resource_id"] if view["resource_id"] is not None else "",
                    "content_description": view["content_description"] if view["content_description"] is not None else "",
                    "class": view.get("class", ""),  
                    "bounds": view.get("bounds", [])  
                }
                
                if len(widget["bounds"]) == 2:
                    widget["bounds"] = [widget["bounds"][0][0], widget["bounds"][0][1],
                                        widget["bounds"][1][0], widget["bounds"][1][1]]
                
                if not any(existing_widget["text"] == widget["text"] and 
                          existing_widget["resource_id"] == widget["resource_id"] and
                          existing_widget["content_description"] == widget["content_description"]
                          for existing_widget in output[activity]):
                    output[activity].append(widget)
                    total_widgets += 1  
  
    print(f"find {total_widgets} widgets")
    print(f"in {len(output)}  Activities:")
    
    for activity, widgets in output.items():
        print(f"  - {activity}: {len(widgets)} 个widget")
   
    if output_file:
        import json
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"save to file: {output_file}")


async def main():
    # state directory path in the output
    app_name = "omninotes"
    state_dir_path = "./Droidbot/droidbot/output/omninotes/6.1.0/states/"

    widget_raw_data = load_all_json_file(state_dir_path)
    widgets_file_path = "output/omninotes/6.1.0.json"
    get_widget_info(widget_raw_data,"omninotes",widgets_file_path)
    output_file = "output/omninotes/annotation_" + os.path.basename(widgets_file_path)
    
    output = await generate_widget_annotations(app_name, state_dir_path, widgets_file_path)
    
    print(f"Generated annotations for {sum(len(v) for v in output.values())} widgets across {len(output)} activities.")
    # save results to json file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Annotations saved to {output_file}")
    
    generate_final_widget_annotation(output_file)

if __name__ == "__main__":
    asyncio.run(main())