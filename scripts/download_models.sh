#!/bin/bash

mkdir -p models
gdown https://drive.google.com/file/d/1rVj_YTQ1rLYHT9enbi8XExWnHUpDQ6Je/view?usp=sharing -O models.zip
unzip models.zip
rm models.zip

# pip install gdown
# bash download_models.sh