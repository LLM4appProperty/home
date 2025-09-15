# Replication Package

This repository contains all the artifacts (including the source code of iPBT, the designed prompts, the dataset of property descriptions) in our paper.

## Directory Structure

    important files and directories in the replication package are as follows:

    |

    |--- iPBT:                                   The source code of iPBT, which focuses on generating executable properties from property description
        |
        |--- Droidbot:                           The source code of the automated app exploration tool, which is implemented on Droidbot.
        |
        |--- generate_widget_annotation.py       The source code of widget context construction phase.
        |
        |--- generate_executable_property.py     The source code of executable property generation phase.
    |--- Properties:                             The properties used in the evaluation

## iPBT

iPBT is a novel property translation tool designed to translate user-provided property descriptions in natural language to executable properties.

### :file_folder:Download

```
git clone https://github.com/LLM4appProperty/home
```

### 💻Environment

As iBPT needs to analysis the GUI information on mobile apps, you need:

- Android SDK
- Android emulator or device
- Java, Python >= 3.8

To run the automated app exploration tool, you need to install the modified droidbot:

```
cd iPBT/Droidbot
cd Droidbot
pip install -e .
```

If you successfully installed it, you are able to execute `droidbot -h`

Also, as iPBT relies on the power of LLM, you should have the API keys to call the service.

### 🔨Setting up emulator

You can create an emulator before running iPBT. See [this link](https://stackoverflow.com/questions/43275238/how-to-set-system-images-path-when-creating-an-android-avd) for how to create avd using [avdmanager](https://developer.android.com/studio/command-line/avdmanager).
The following sample command will help you create an emulator, which will help you start using iPBT s quickly：

```
sdkmanager "build-tools;29.0.3" "platform-tools" "platforms;android-29"
sdkmanager "system-images;android-29;google_apis;x86"
avdmanager create avd --force --name Android10.0 --package 'system-images;android-29;google_apis;x86' --abi google_apis/x86 --sdcard 1024M --device "pixel_2"
```

Next, you can start one emulator and assign their port numbers with the following commands:

```
emulator -avd Android10.0 -read-only -port 5554
```

### 🔆 Usage

#### Dynamic exploration on mobile apps

The automated app exploration is built on [Droidbot](https://github.com/honeynet/droidbot), a popular test input generator for Android apps. Note that we implement a random exploration strategy in the file `input_policy.py`.

```
droidbot -a <APK_FILE> -o <OUTPUT_FILE> -d <DEVICE_SERIAL>
```

You can also set the timeout of the exploration `-timeout`. The default exploration strategy is the random exploration.

After the exploration on the app, you should get the exploration results in the <OUTPUT_FILE>.

#### Widget context construction

After exploration on the app, iPBT can construct the widget context from the exploration results by executing `generate_widget_annotation.py`.

You can modify the parameters in `generate_widget_annotation.py` for different apps or runs.

* state_dir_path: the exploration result from the Dynamic exploration phase.
* output_file:    the path of the widget context construction result.

#### Executable property generation

You can write the property descriptions in the form of <P,I,Q>. 
* P is the precondition, which defines when or where we could check the property. 
* I is the interaction scenario, which
defines how to perform the functionality. 
* 𝑄 is the postcondition, which defines the expected
results are after the functionality. 

For more details about how to write a property, see [Kea](https://github.com/ecnusse/Kea).

Then, together with the Widget context, you can generate the executable property by executing `generate_executable_property.py.`

After that, you can get the generated executable properties.
