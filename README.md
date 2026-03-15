
## Dark Sky Multi-Cam


## Detecting Events in the Night's Sky Using Low-Resolution Cameras

Brody Kladis


## 


## Introduction 

The Global Meteor Network[^1] (GMN) is an open-source project aiming to make a network of cameras pointing up at the night sky all across the world, observing objects as they enter and burn up in Earth's atmosphere. The data they collect is used in predicting meteor shower intensities for hobbyists, and perhaps more importantly, in collecting information about the formation of our solar system. By observing attributes about meteors such as their color, intensity, and trajectory, we can gather important information about where meteors came from and what the makeup of our solar system may have looked like when they were created.

Visual data allows us to collect a lot of info about meteor observations, but it can be hard to identify when we have observed a meteor as opposed to other sources of false detections. As such, only bright, large, obvious detections are utilized as data. Fewer than 1% of meteors are visible to the naked eye, and far fewer than that will actually be captured as positive detections by GMN.[^2] What if there were some way to increase our ability to distinguish signal from noise– some way to increase the accuracy of detections, and be able to record data for much smaller meteors? This project aims to do exactly that. 


## Concept of Methods

Two simple definitions:



* Event: something is moving within a camera's field of view
* Interesting event: something *in space* is moving within the camera's field of view (satellites & meteors) 

Imagine a camera looking at the stars with no astronomical events happening. We assume that photons hit a camera's sensor as modeled by a Poisson random variable; each photon arrives independently, and f(photon hitting sensor) at any given time is constant when we assume no events are happening. We next assume that this Poisson arrival of photons corresponds to a pixel intensity, as observed by the camera, to be approximately normal. The mean and variance of the pixel can be calculated from observations of that pixel over time. 

If we have a pixel governed by $N\left(\mu, \sigma^{2}\right)$, then we can apply the null hypothesis that any variations in pixel intensity are purely due to random noise. Then, for every frame, we can calculate a p-value of pixel intensity. If a p-value is low, then we believe that it is likely that some event is happening. 

This idea of motion detection is nothing truly unique. Similar things have been done with the concept of motion masks, as shown to the right.[^3] Where this concept differs from anything else done before is the use of multiple cameras. In this project, four cameras point at the same point in the sky with the same orientation. If we assume light hits the cameras independently when there is no event, we can average out the light intensity at a given pixel position across all four cameras, reducing the noise in pixel intensity and making it easier to identify signals. 

The cameras also have some distance between them. Due to this distance between cameras, objects that are close to the camera will appear in different pixel positions across all four cameras. As you approach the limit case where an object is infinitely far from the camera (see derivation 1 for why this is a fair assumption), objects appear in the same pixel position for each camera. This uses a “wisdom of the crowds” style of approach, where many noisy observations can reliably make correct predictions. Using this idea, we can distinguish between boring events (e.g., a bug hovers near a camera, a bird flies overhead) and interesting events in the sky. 

See the appendix for a detailed “under the hood” math behind detection classification. 


## Project Implementation

The Dark Sky Multi-Cam is a device consisting of four Walfront USB webcams.[^4] The cameras are 1 megapixel (quite low-quality for astronomy) and 30fps. I hoped to use these cheap and simple cameras as a proof of concept and a stepping stone to being capable of much more difficult detections later on. 

A 3D printed body was made for the camera, angling each of the webcams in the same direction. From the device, the cameras simply connect via USB cable to my laptop, where a script manages synchronized frame rates and exposure times. 

The data pipeline is implemented as follows:



* Record the night sky from each of the four cameras
* Use star positions to correct for slight imperfections in camera alignments to ensure the same pixel position in all cameras corresponds to the same position in the night sky
* For all pixel positions in all frames, find the probability of noise causing the observation
* If that probability is sufficiently small, we assume there was a detection. 


## Testing

Initial testing was done from my dorm, and used to preliminarily tune parameters, test code, and get the method working. The code was developed by only ever looking at footage from the initial tests. After collecting final data, nothing was changed as to ensure this method could be generally applicable to ANY footage. 

Final testing was done at Pescadero Point, an area with low light pollution, increasing the odds of observing anything interesting. Footage was collected between the time of sunset and when Officer Mitchell kicked me for trespassing after dark. I collected 20 minutes of data and prayed to God that I would see anything. 


## Results

Setting a confidence level to p &lt; (1/30)10<sup>-6</sup> and using a resolution of 10<sup>6</sup> pixels per frame times 30 frames per second, we expect about one false detection per second (another Poisson process!). While false positives are isolated points, when there is a signal, it is immediately and clearly visible as a series of detections that are continuous over time and space. This is exactly what we see in our results. 

The three images all show the same moment in time as a satellite is passing overhead. The image below on the left shows the raw video output of a single camera. You can see almost nothing in the raw image, and I challenge you to zoom in and identify how the satellite appears in the frame as just a few pixels— however, the images to the right trace the satellite's path as detected by the program. The plot at the top shows detections over time, clearly distinguishing isolated false positives from real signals. This is echoed in the screenshot below, which shows 3 seconds of detections overlaid on the video. 


## Implications

If you wanted to set up your own all-sky camera today to contribute to an open-source network, you would need to invest a thousand dollars into a camera.[^5] The sensor array I built cost less than a hundred dollars, and produced a greater accuracy than I have seen out of any hobbyist alternatives. This algorithm can be used to significantly amplify the power of visual detections. This test proved accurate satellite detection, and there's no reason to expect any different results for meteors. Unfortunately, no major meteor showers occurred within the timeline of the project, but I intend to continue testing when the Perseids shower comes around later in the month. 

The ability to use cheaper cameras could make it more accessible for individuals to contribute to open-source projects for astronomical observations. A modified version of this method could allow for nearby camera arrays to combine data to make predictions even more accurate. For astronomical purposes, this could have profound impacts. Each meteor is a piece of archeological evidence that we only get one chance to observe. 

Making it cheaper to add new sensors to a network and making those sensors more accurate could significantly increase the data we gather. As you add more cameras to a single sensor array, it gets exponentially less likely that a false detection occurs, meaning you can set much lower confidence levels for detections. Adding more sensor arrays to a network both increases the area of coverage, and areas in which camera coverage overlaps can have increased accuracy. As such, you create a network that can grow exponentially in detection capability with each camera added. Further implementation of this project has the potential to answer questions about our solar system's early days, identify which other regions of space meteors originate from, and use trajectory info to discover previously unknown comets. 


## Appendix


### Github Repository

[brody-kladis/dark-sky-multi-cam](https://github.com/BrodyKladis/Dark-Sky-Multi-Cam) 

The repository includes the following:



* The Python script used to run the four cameras together in the Night Sky Multi-Cam
* A script was made that can correct for small differences in camera angles. It works by presenting a human with the same frame across two videos and prompting the user to map two stars onto one another. It then repeats many times to get multiple reference points for each video. It then calculates a coordinate transform to map videos 2, 3, and 4 onto video 1. 
* A script that creates a cumulative motion map, displaying an image that visualizes the variance of each pixel throughout the course of the video. This was not discussed in my paper, but this was done as a check of my methods to identify sources of variance and help inform my methods. 
* Various detections, photos, and other media pertaining to the project


### Google Drive

[Google Drive Folder](https://drive.google.com/drive/folders/1ijg4qAf8nNXSsnGxLjZKHNQeEyZ0KKwO?usp=sharing)

The drive contains the following:



* Preliminary test footage that was used to tune my method and verify some concepts
* The final test footage that was collected at Pescadero Point
* Fusion360 CAD file for the camera mount
* Various media of this project


### 


### Under-the-Hood Math

Let's model the behavior of a single pixel.
Start with the assumption that there is no event occurring at a given pixel.

The light hitting a camera sensor at a specific pixel position is given by a Poisson process. For a high $\lambda$, the Poisson process can be effectively modeled as a Gaussian.

Let I be the intensity of a single pixel.

$$
\begin{aligned}
I \sim \text { Poi }(\lambda) & \Rightarrow \text { high lambda } \Rightarrow I \sim N\left(\mu, \sigma^{2}\right) \\
\mu & =\text { mean intensity of a pixel } \\
\sigma^{2} & =\text { variance of pixel intensity }
\end{aligned}
$$

Because the environment may change over time due to stars moving or weather/lighting changing, the mean and variance defining the distribution of pixel intensity will change. To account for the slow change in mean and variance, the two values are constantly recalculated by the method of Exponential Moving Average (EMA). EMA is a method in which the parameters move slightly to match the values observed in frame i. $\alpha$ defines the amount by which parameters change, where a higher value of alpha represents a greater change per frame, while a lower alpha is less adaptable to changes, but more stable.

$$
\begin{gathered}
\mu_{i+1}=(1-\alpha) \mu_{i}+\alpha \cdot x_{i} \\
\sigma_{i+1}^{2}=(1-\alpha) \sigma_{i}^{2}+\alpha \cdot\left(\mu_{i}-x_{i}\right)^{2}
\end{gathered}
$$

Now, let's look at the probability that a single camera would see a pixel intensity of at least x given the parameters as evaluated at the current frame:

$$
P(I>x)=1-\phi\left(\frac{x-\mu_{i}}{\sigma_{i}}\right)
$$

Where this gets interesting is when we consider multiple cameras. Because we are still working with the assumption that there is no event and that intensity is a Poisson process, the intensity seen by each camera is independent. Let an observation be the intensity, $\mathrm{x}_{\mathrm{n}}$, seen by each camera for a given pixel.

$$
P(\text { observation is due to chance })=P\left(I_{1}>x_{1}, I_{2}>x_{2}, \ldots, I_{n}>x_{n}\right)=\Pi\left(1-\phi\left(\frac{x_{n}-\mu_{i, n}}{\sigma_{i, n}}\right)\right)
$$

where ' $i$ ' iterates over frames, ' $n$ ' iterates over cameras

P(observation) gives the probability that an observation would occur given the assumption of a Poisson process. If we make an observation that is incredibly unlikely, it means that the Poisson assumption is likely not true. The assumption of a Poisson distribution is only significantly broken when an interesting event occurs. As such, P (observation due to chance) is a useful tool in measuring whether a given observation represents signal or noise. The math under the hood actually computes log probability to prevent underflow errors as probabilities approach incredibly low orders of magnitude:

$$
\log (P(\text { observation is due to chance }))=\Sigma \log \left(1-\phi\left(\frac{x_{n}-\mu_{i, n}}{\sigma_{i, n}}\right)\right)
$$


<!-- Footnotes themselves at the bottom. -->
## Notes

[^1]:
     [Global Meteor Network](https://globalmeteornetwork.org/about/)

[^2]:
     [Britannica - Basic Features of Meteors](https://www.britannica.com/science/meteor/Basic-features-of-meteors?utm_source=chatgpt.com)

[^3]:
     [Medium - Introduction to Motion Detection](https://medium.com/@itberrios6/introduction-to-motion-detection-part-1-e031b0bb9bb2)

[^4]:
     [Amazon - Walfront USB Webcam Product Listing ](https://www.amazon.com/dp/B08MXVDY2B?ref=ppx_yo2ov_dt_b_fed_asin_title)

[^5]:
     [All Sky Camera Product Listing - OPT](https://optcorp.com/collections/all-sky-cameras?srsltid=AfmBOooAZHm6gC2bfEXez9zujgV7Z4cq2CaqsGazmzSIm_nCYTDbVQlb )
