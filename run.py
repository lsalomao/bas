import uvicorn

if __name__ == "__main__":    
    uvicorn.run("app.main:app", port=2555, reload=True)