class MLModel:

    def __init__(self, model_path):
        self.model_path = model_path

    @classmethod
    def from_pretrained(cls, model_name):
        path = f"/models/{model_name}.bin"
        return cls(path)

    @classmethod
    def from_config(cls, config_dict):
        path = config_dict["model_path"]
        return cls(path)
    

model1 = MLModel("/local/model.bin")
model2 = MLModel.from_pretrained("bert")
model3 = MLModel.from_config({"model_path": "/remote/model.bin"})