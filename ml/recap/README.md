# Stitch ( `Stitch.py`)

This function/script processes a pre-scored CSV file and a directory of source videos to automatically generate a compiled recap `.mp4` file. It is the video processor in the pipeline and will execute physical cuts and merges using FFmpeg without re evaluating any algorithms.

## Requirements

* Python 3.x
*  `pandas`
* FFmpeg ( `brew install ffmpeg` on macOS)

## Usage

Run the script from the command line by passing these 3 required args:

python stitch.py <scores_csv> <video_dir> <out_path>

Example Execution:

python stitch.py scores.csv ../scoring_david/ recap.mp4

## Inputs

###1.  `scores.csv`
A CSV file containing the scored 5-second video windows. The script requres the following columns to execute the extraction logic correctly:

* `video`: The exact filename of the source video (e.g., `five_min_vid.MOV`)
* `start_seconds`: The start time of the clip in seconds (float)
* `end_seconds`: The end time of the clip in seconds (float)
* `score`: The calculated algorithmic score for the window (float)

### 2. Video Directory (`video_dir`)
A local directory containing all source video files referenced in the `video` column of the CSV. File names in this directory must perfectly match the CSV references to prevent execution failure

## Output

### `<out_path>` (e.g., `recap.mp4`)
Output is a single merged `.mp4` file containing the compiled highlight.

* Duration: It targets 60 seconds (max of 5 second clips). However, the final duration depends on the number of valid rows in source CSV. 

* Selection logic: clips are prioritized and extracted in desc. order based on the 'score' metric

* Pacing filter: there is a strict 20 secong gap filter to reject overlapping timelines and ensure the highlight video spans the chronological udration of the source footage

* Chronology: selected clips are chronologically sorted by `start_seconds` prior to rendering

* Encoding: standarized to  `libx264` with the `yuv420p` pixel format to ensure native Apple quicktime functionality and iOS playback compatibility. For windows, the `libx264` and `yuv420p` will also play fine with windows media player and modern web browsers.



