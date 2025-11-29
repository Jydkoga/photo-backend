def extract_public_id(url):
    filename = url.split("/")[-1]
    public_id = filename.split(".")[0]
    return public_id
