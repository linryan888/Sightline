SIG_65 ML Scoring Pipeline MVP

# Tech Stack

We used Ultralytics YOLO11n. we used their Nano version, which only 
requires a CPU and not a dedicated graphics card. 

Since it is a MVP, we used YOLO11n to start off since its lightweigt and fast on mac cpu. It also provides a really reliable signal for us to use (in our case, identifying objects) to serve as our activity count (finding what is most interesting).

# Signals and Weights 

* All configurations are handled in 'config.yaml'
* We used 'signal_yolo_count' as our signal. This means we evaluate only 1 single image to represent each 5 second chunk of video. So 1 image is used in the exact frame right in the middle (at 2.5 seconds, 7.5 secs, etc.)
* We only used the 5 second 'window_length' setting to match the backend requirements. We didn't use any other weights or thresholds.
* We use normalization to bound a score between 0.0 and 1.0. Specifically, we use min max normalization within the video's dataset.

# Required Constraints addressed

* double counting across frames: we avoided that. The script extracts and runs inferences on exactly 1 frame (midpoint in this case) per each 5 second window. It doesn't scan consecutive frames, so its not possible to double count the same object. 
* Time spread and variety: Implemented a time distance filter. The script forces a minimum 20 second gap between selected high scoring clips to ensure the 6 to 12 window recap covers different parts of th timeline. 


* We didn't measure accuracy because SIG-62 was not completed.

* We used Macos CPU. It processed a 1 minute video in 10 seconds. Processed 5 minute video in about 44 seconds. 

# Flaws and 3 improvements:

* We only used 1 model. Here, YOLO doesn't understand context or movement; it just identifies objects. When I pointed it at a static row of locked bikes, it outputted a massive object count and a score of 1.0 (the max) even though this isn't interesting. We need more than just YOLO. 

* Improvement 1: implement CLIP embeddings to filter out visually repeatitive or static scenes. So this means implement semantic context. 
* Improvement 2: Add Whisper/VAD or another audio detection model to detect audio spikes or human speech. This is really important since we're humans and can indicate interesting interactions.

* Improvement 3: Switch from static single frame counting to YOLO's tracking mode over a 1 second sample to measure actual object movement and speed and trajectory (like a moving dog). 
