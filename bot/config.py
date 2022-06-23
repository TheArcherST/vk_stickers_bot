import yaml


CONFIG_PATH = './config.yaml'

with open(CONFIG_PATH) as fs:
    config = yaml.safe_load(fs)
