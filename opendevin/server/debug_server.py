import uvicorn

if __name__ == '__main__':
    uvicorn.run('debug_server:app', host='0.0.0.0', port=3000, workers=8)
