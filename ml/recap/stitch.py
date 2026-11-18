import pandas as pd
import subprocess
import os
import sys
import tempfile

# scores_csv = sys.argv[1]
# video_dir = sys.argv[2]
# out_path = sys.argv[3]


empty = []

#params are (video, start_seconds, end_seconds, score)
# we use 5 second windows

def stitch (scores_csv,video_dir ,out_path,target_seconds=60):
    """video processor to read scores.csv and create the cuts for the recap video, targeting 60 seconds."""
    selected_clips = []


    df = pd.read_csv(scores_csv)
    df = df.sort_values(by="score", ascending=False)

    print(df.head())

    #clip selecting pre processing
    for index, row in df.iterrows():
        if len(selected_clips) >=  12:  
            break
        conflict = False
        for i in selected_clips:
            if row['video'] == i['video'] and abs(row['start_seconds'] - i['start_seconds']) < 20:
            #to avoid video timeline overlap < 20
                conflict = True
                break

        if conflict == False:
            selected_clips.append(row.to_dict())

    print(len(selected_clips))

    selected_clips = sorted(selected_clips, key=lambda x: x['start_seconds'])

    for clip in selected_clips:
        print(clip)

    #finished with clip selection pre processing
    with tempfile.TemporaryDirectory() as temp_dir:
        clip_paths = []

        for i, clip in enumerate(selected_clips):
            vid_path = os.path.join(video_dir, clip['video'])
            out_clip = os.path.join(temp_dir, f"clip_{i}.mp4")
            #implemented seeking to jump to video file's internal index and not process those before it.

            command = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-ss", str(clip['start_seconds']),
                "-to", str(clip['end_seconds']), 
                "-i", vid_path, 
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", out_clip
            ]
            print(" ".join(command))
            subprocess.run(command, check=True)
            clip_paths.append(out_clip)
        concat_file = os.path.join(temp_dir, "concat.txt")

        with open(concat_file, "w") as f:
            for cp in clip_paths:
                f.write(f"file '{cp}'\n")
        merge_command = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            out_path
            
        ]
        subprocess.run(merge_command, check=True)



if __name__ == "__main__":
    scores_input = sys.argv[1]
    video_input = sys.argv[2]
    output_name = sys.argv[3]

    stitch(scores_input, video_input, output_name)

    