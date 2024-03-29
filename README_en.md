# Self-driving-go car based on Remote Controlled GoPiGo3

In this project we remotely control a GoPiGo3 self-driving car via a mobile device or a laptop.

![Self-driving Go](images/self_driving_go.jpg)

## Requirements

We need the following components for this project:

* A [GoPiGo3](https://www.dexterindustries.com/gopigo3/) robot - it also includes the battery pack.
* A [Raspberry Pi](https://www.dexterindustries.com/raspberry-pi/).
* A [Pi Camera](https://www.dexterindustries.com/shop/raspberry-pi-camera/).
* A laptop or a mobile device (aka smartphone).
* A Linux Box with GPU (which supports Nvidia Cuda library for Keras)

## Setting Up

In order to proceed the setup, make sure you have the `GoPiGo3` repository installed (not just cloned, but also installed) or that you have the latest version of `Raspbian For Robots`.

After going through the above paragraph, install the `Pi Camera` dependencies and `Flask` by running following command:
 ```
 sudo pip3 install -r requirements.txt
 ```

You should now have everything set up.

## Running it

Start the server by typing the following command:
```
python3 remote_robot.py
```
It's going to take a couple of seconds for the server to fire up.
The web app is set to port `5000` whereas the video stream is found at port `5001`.

If you have got `Raspbian For Robots` installed, then going to `http://dex.local:5000` address will be enough.
If you don't have `Raspbian For Robots`, then you'll need to see what's your interface's IP address.

Also, please make sure you have your mobile device / laptop on the same network as your `GoPiGo3`. Otherwise, you won't be able to access it.

## Generating training data
* use Keyboard to drive the self-drive car instead of mouse joystick
* arrow keys:
  * up - forward
  * left - left
  * right - right
  * space - break to stop
  * q - speed up by increasing throttle
  * w - sepped down by decreasing throttle
  * p - turn on the lights
  * o - turn off the lights

## Run self-driving-go
* training data will be generated on the raspberry folder ~/test/training
* tar cvzf training_left.tgz training/*

Each round you need to tar and zip for retaining previous data

## Run jupyter notebook on your linux box for deep learning
1. open self-driving-go.ipynb
2. get the model.h5 at the end of training
3. upload model.h5 on raspberry pi

![Deeplearning training](images/training_result.jpg)

## Run self-driving-go with trained model
(This time you don't need to drive it but watch it out for unexpected behaviour)

```
$ python3 self_driving_go.py
```

## Setting Up to Run on Boot
You can run the server on boot so you don't have to run it manually.  Use the command
`install_startup.sh`
and this should start the flask server on boot.  You should be able to connect to the robot using "http://dex.local:5000" or if using the Cinch setup, you can use "http://10.10.10.10:5000"

You can setup Cinch, which will automatically setup a wifi access point, with the command
`sudo bash /home/pi/di_update/Raspbian_For_Robots/upd_script/wifi/cinch_setup.sh`
On reboot, connect to the WiFi service "Dex".

## YouTube Video

Here's a YouTube video of this project:

[![Self Driving Go](images/self_driving_go_youtube.jpg)](https://youtu.be/S1khLwfSIi8)
