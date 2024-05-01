import discord
from discord.ext import commands
import websocket
import json
import uuid
from PIL import Image
import io
import urllib.request
import random
from discord import option
import math

bot = discord.Bot()
server_address = "127.0.0.1:8188"
client_id = str(uuid.uuid4())

prompt_text = open('workflow_api_zhuoyue.json').read()
current_json = "zhuoyue_sdxl"

def queue_prompt(prompt):
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    req = urllib.request.Request(f"http://{server_address}/prompt", data=data)
    return json.loads(urllib.request.urlopen(req).read())

def get_images(ws, prompt):
    prompt_id = queue_prompt(prompt)['prompt_id']
    output_images = {}
    current_node = ""
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message['type'] == 'executing':
                data = message['data']
                if data['prompt_id'] == prompt_id:
                    if data['node'] is None:
                        break  # Execution is done
                    else:
                        current_node = data['node']
        else:
            if current_node == 'save_image_websocket_node':
                images_output = output_images.get(current_node, [])
                images_output.append(out[8:])
                output_images[current_node] = images_output

    return output_images

intents = discord.Intents.default()
# bot = commands.Bot(command_prefix='!', intents=intents)

def change_workflow(workflow):
    global prompt_text
    prompt_text = open(f'{workflow}.json').read()

@bot.slash_command(name='swap_model', description='Swap the model used for generation')
async def swap_model(ctx: discord.ApplicationContext):
    await ctx.defer()
    global current_json
    # swap to different model
    if current_json.split("_")[1] == "sdxl":
        current_json = current_json.split("_")[0] + "_" + "zhuoyueaixl"
    else:
        current_json = current_json.split("_")[0] + "_" + "sdxl"
    change_workflow(current_json)
    await ctx.respond(content=f"{ctx.author.mention}, the model has been swapped to {current_json.split('_')[1]}.")
    

@bot.slash_command(name='generate', description='Generate an image from a prompt')
@option(
        'Text',
        str,
        description='Your text to produce the prompt.',
        required=True,
    )
@option(
        'Seed',
        str,
        description='Seed for the random number generator.',
        required=False,
)
# aspect ratio
@option(
        'Aspect Ratio',
        str,
        description='Aspect ratio of the generated image. Width/Height. Must be between 0.5 and 2.',
        required=False,
    )
async def generate(ctx: discord.ApplicationContext, prompt: str, seed: str = None, aspect_ratio: str = None):
    await ctx.defer()


    ws = websocket.WebSocket()
    ws.connect(f"ws://{server_address}/ws?clientId={client_id}")
    
    global current_json
    if "zhuoyue" in prompt or "zhuo yue" in prompt:
        current_json = "zhuoyue" + "_" + current_json.split("_")[1]
    elif "yuai" in prompt:
        current_json = "yuai" + "_" + current_json.split("_")[1]
    else:
        current_json = "null" + "_" + current_json.split("_")[1]
        
    change_workflow(current_json)
    
    # Modify the prompt to use the user's input
    prompt_data = json.loads(prompt_text)
    prompt_data["6"]["inputs"]["text"] = prompt
    if seed is not None:
        try:
            seed = int(seed)
        except ValueError:
            await ctx.respond(content=f"{ctx.author.mention}, the seed must be a number.")
            return
    else:
        seed = random.randint(0, 1000000)
    prompt_data["3"]["inputs"]["seed"] = seed
    if aspect_ratio is not None:
        try:
            aspect_ratio = float(aspect_ratio)
        except ValueError:
            await ctx.respond(content=f"{ctx.author.mention}, the aspect ratio must be a number.")
            return

        if aspect_ratio < 0.5 or aspect_ratio > 2:
            await ctx.respond(content=f"{ctx.author.mention}, the aspect ratio must be between 0.2 and 5.")
            return
        

        # get width and height that equal w*h == 1024*2 and w/h = aspect_ratio
        height = math.sqrt(1024*1024/aspect_ratio)
        width = 1024*1024/height

        # round to the nearest 32 pixels
        height = round(height/32)*32
        width = round(width/32)*32
        
        prompt_data["5"]["inputs"]["width"] = width
        prompt_data["5"]["inputs"]["height"] = height
        
    else:
        width = 1024
        height = 1024
        prompt_data["5"]["inputs"]["width"] = width
        prompt_data["5"]["inputs"]["height"] = height
    
    images = get_images(ws, prompt_data)
    
    files_to_send = []
    for node_id in images:
        for image_data in images[node_id]:
            image = Image.open(io.BytesIO(image_data))
            with io.BytesIO() as image_binary:
                image.save(image_binary, 'PNG')
                image_binary.seek(0)
                files_to_send.append(discord.File(fp=image_binary, filename=f'image_{node_id}.png'))

    # Reply to the user and mention the prompt in code blocks
    message_content = f"{ctx.author.mention}, \nseed: `{seed}` - Aspect Ratio: `{aspect_ratio}`  - Size: `{width}` x `{height}`\nprompt:\n```\n{prompt}\n```"
    await ctx.respond(content=message_content, files=files_to_send)
    

    ws.close()

# load from .env file
import os
from dotenv import load_dotenv
load_dotenv()

bot.run(os.getenv("DISCORD_TOKEN"))
