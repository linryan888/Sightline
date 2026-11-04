import argparse
import yaml
import csv
import os
import subprocess
import glob
import cv2 
from ultralytics import YOLO

def score_video(video_path):
    model = YOLO("yolo11n.pt")
    window_size = 5
    
    cap = cv2.VideoCapture(video_path) 
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    if fps == 0:
        print(f"Sjipping {video_path}: i could not read this video FPS.")
        return []
        
    duration = frame_count / fps

    windows = []



    # window_size = config.get('window_length', 5)
    
    for start in range(0, int(duration), window_size): #each window size is 5 seconds and will iterate
        #through the video timelinee in chunks (like 0-5s, 5-10s)
        end = min(start + window_size, duration)
        #so our chunk doesn't exceed the totaal video length


        if end - start < 1:
            continue
            
        middle_time = start + ((end - start) / 2)
        cap.set(cv2.CAP_PROP_POS_MSEC, middle_time * 1000)#gets the millisecond in the video (jumps right to it)

        
        ret, frame = cap.read() #will get the single frame and extract it as an image array
        #^ prevents the model from processing 30 frames per second, saves us some computing power/time

        
        if not ret:
            continue
            
        results = model(frame, verbose=False) #will pass that frame variable to YOLO11 to detect objects
        
        object_count = len(results[0].boxes) #counts totaal number of objects YOLO found. 

        #create dict that will store the start, end, raw signal and path file for this window specifically
        windows.append({
            'start_seconds': start,
            'end_seconds': end,
            'signal_yolo_count': object_count,
            'filepath': os.path.abspath(video_path),
            'video': os.path.basename(video_path)
        })
        
    cap.release()
    
    if windows:
        counts = [w['signal_yolo_count'] for w in windows] #all of our object counts from the video (store)
        min_val = min(counts) #lowest and highest object counts (min and max)
        max_val = max(counts) 
        
        for w in windows:
            if max_val == min_val: #earlier we had a bug that hit zero divison error so we add this to prevent that.
                w['score'] = 0.5
            else:
                w['score'] = (w['signal_yolo_count'] - min_val) / (max_val - min_val) #bounds from 0.0 to 1.0
            
    return windows


# def setup_environment():
#     #here, we parse cli arguments and load the yaml configuration
#     parser = argparse.ArgumentParser()
#     parser.add_argument('--video', required=True, help='Directory of vidoes or paths to a single video')

#     parser.add_argument('--config', required=True, help='path to config.yaml')
    
#     parser.add_argument('--out', required=True, help='output directory')
#     args = parser.parse_args()

#     os.makedirs(args.out, exist_ok=True)

#     with open(args.config, 'r') as f:
#         config = yaml.safe_load(f)

#     return args, config

def get_video_file(video_path):

    #will retunr a lst of all valid video files from the provided video_path
    if os.path.isdir(video_path):
        files=[]

        for ext in ('*.mp4', '*.mov', "*.avi"): #video file types!:
            files.extend(glob.glob(os.path.join(video_path, ext)))
        return files
    return [video_path]

def write_scores_csv(windows, out_dir):
    #writes the window data to scores.csv

    csv_path = os.path.join(out_dir, 'scores.csv')

    with open(csv_path, 'w', newline='') as csvfile:
        fieldnames = ['video', 'start_seconds', 'end_seconds', 'signal_yolo_count', 'score']

        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()


        for w in windows:

            writer.writerow(w)

    print(f"scores will be written to : {csv_path}")


def generate_recap(windows, out_dir):
    #will filter top windows and stiches them using ffmpeg. this one
    #will enforce a time-spread and stiches them.
    windows.sort(key=lambda x: x['score'],  reverse=True)

    selected_windows = []

    min_time_gap = 20

    for w in windows:
        too_close = False
        for sel in selected_windows:
            if abs(w["start_seconds"] - sel["start_seconds"]) < min_time_gap:
                too_close = True
                break
        if not too_close:
            selected_windows.append(w)

        if len(selected_windows) == 12:
            break

    selected_windows.sort(key=lambda x: x["start_seconds"])

    print(f"Selected {len(selected_windows)} spread-out windows for the recap.")

    concat_file = os.path.join(out_dir, 'concat.txt')

    with open(concat_file, 'w') as f:
        for w in selected_windows:
            f.write(f"file '{w['filepath']}'\n")

            f.write(f"inpoint {w['start_seconds']}\n")


            f.write(f"outpoint {w['end_seconds']}\n")



    recap_path = os.path.join(out_dir, 'recap.mp4')

        # DEVNULL is removed so you can actually read the error
    subprocess.run([
        'ffmpeg', '-y', '-f', 'concat', '-safe', '0', 
        '-i', concat_file, 
        '-map', '0:v',     # this will grab only the video stream
        '-c:v', 'copy',    # we copy it without trying to re-encode
        recap_path])

    print(f"recap saved to {recap_path}")
        

# def main():
#     args, config = setup_environment()

#     print(f"loading model {config['model_type']} is ")

#     model = YOLO(config["model_type"])

#     video_files = get_video_file(args.video)

#     all_windows = []

#     for vf in video_files:
#         print(f"processing {vf} as " )
#         v_windows = score_video(vf, config, model)
#         all_windows.extend(v_windows)
#     write_scores_csv(all_windows, args.out)
#     generate_recap(all_windows, args.out)

import argparse
import csv
import subprocess

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SIG-49 Scoring Pipeline MVP")

    parser.add_argument("--video", required=True, help="Path to video file or directory")

    parser.add_argument("--config", required=True, help="Path to config file")

    parser.add_argument("--out", required=True, help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    
    video_paths = []
    if os.path.isdir(args.video):


        video_paths = [os.path.join(args.video, f) for f in os.listdir(args.video) if f.endswith(('.mp4', '.mov', '.MOV'))]
    else:
        video_paths = [args.video]
        
    all_windows = []
    for vp in video_paths:

        windows = score_video(vp)

        all_windows.extend(windows)
        
    csv_path = os.path.join(args.out, "scores.csv")

    with open(csv_path, mode="w", newline="") as f:

        writer = csv.DictWriter(f, fieldnames=["video", "start_seconds", "end_seconds", "signal_yolo_count", "score"])
        writer.writeheader()

        for w in all_windows:

            writer.writerow({k: w[k] for k in ["video", "start_seconds", "end_seconds", "signal_yolo_count", "score"]})
            
   
   
    print(f"Scores written to {csv_path}")

    generate_recap(all_windows, args.out)

    