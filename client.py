import socket
import sys
import os
import concurrent.futures
from pathlib import Path

# get domain from the full origin link
def getDomain(link):
    if("http://" in link):
        domain = link[link.find("http://") + 7:]
    elif("https://" in link):
        domain = link[link.find("https://") + 8:]
    else:
        domain = link[link.find("www."):]
    return domain.split("/")[0]

# get file name from the full origin link
def getFileName(link):
    file_name = link.rsplit('/', 1)[-1]
    if(file_name == "" or file_name == getDomain(link)):
        file_name = "index.html"
    return file_name

# get link to file from the full origin link
def getLinkExcludeDomain(link, domain):
    link_to_file = link.replace(domain, "")
    link_to_file = link_to_file.replace("http://", "")
    if(link_to_file == ""):
        link_to_file = "/index.html"
    return link_to_file

# create file name
def createFileName(domain, file_name):
    return domain + "_" + file_name

# get content length from data received
def getContentLength(data):
    data_decoded = data.split(b"\r\n\r\n")[0].decode()
    index = data_decoded.find("Content-Length: ")
    contentLength = data_decoded[index + 16:]
    contentLength = contentLength.split("\r\n")[0]
    contentLength = int(contentLength)
    return contentLength

# receive header
def receiveHeader(s):
    data = b""
    while data[-4:] != b"\r\n\r\n":
        data += s.recv(1)
    return data

# Connect by Content-Length
def connectContentLength(s, file, sizeReceived, contentLength):
    while True:
        data = s.recv(sizeReceived)
        if not data:
            break
        contentLength -= len(data)
        file.write(data)
        if contentLength <= 0:
            break

# receive body
def recv_printBody(s, chunkSize, file, sizeReceived):
    while True:
        if chunkSize > sizeReceived:
            data = s.recv(sizeReceived)
        else: 
            data = s.recv(chunkSize)
        chunkSize -= len(data)
        file.write(data)
        if chunkSize == 0:
            break

# receive chunked size
def recvChunkedSize(s):
    data = b""
    while b"\r\n" not in data:
        data += s.recv(1)
    data = data.split(b"\r\n")[0]
    data = data.decode()
    data = int(data, base = 16)
    return data

# pass through the endlien (b"\r\n") after chunked size
def passThroughEndLine(s):
    data = b""
    while b"\r\n" not in data:
        data += s.recv(1)

# Connect by Transfer-Encoding: chunked
def connectChunked(s, file, sizeReceived):
    chunkSize = recvChunkedSize(s)

    # print every Chunked
    while chunkSize != 0:
        recv_printBody(s, chunkSize, file, sizeReceived)
        passThroughEndLine(s)
        chunkSize = recvChunkedSize(s)

# get content length from chunked data
def getContentLengthChunked(data):
    index = data.find(b"\r\n")
    print("index: ", index)
    if index == -1:
        return False
    contentLength = data[:index]
    print("contentLength: ", contentLength)
    return True

# analyze link
def analyzeLink(link):
    file_name = getFileName(link)
    domain = getDomain(link)
    link_exclude_domain = getLinkExcludeDomain(link, domain)
    directory_file = createFileName(domain, file_name)
    return file_name, domain, link_exclude_domain, directory_file

# get directory file path
def getDirectoryFilePath(link_exclude_domain):
    directory_path = link_exclude_domain.rsplit('/')[-1]
    directory_path = link_exclude_domain.removesuffix(directory_path)
    while '/' in directory_path:
        directory_path = directory_path.replace('/', '\\')
    return directory_path

# prepare to connect
def prepareToConnect(link_exclude_domain, domain, directory_file, isHasSubFolder):
    host = socket.gethostbyname(domain)
    port = 80
    format = "utf-8"

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))

    connectionType = "Connection: keep-alive\r\nKeep-Alive: timeout=5, max=100"
    request = "GET " + link_exclude_domain + " HTTP/1.1\r\nHost: " + domain + "\r\n" + connectionType + "\r\n\r\n"
    s.sendall(request.encode(format))

    if not isHasSubFolder:
        file = open(directory_file, "wb")
        sizeReceived = 1024
        header = receiveHeader(s)

        return s, file, sizeReceived, header

    current_directory = os.getcwd()
    if "." in (link_exclude_domain.rsplit('/')[-1]):
        directory_path = getDirectoryFilePath(link_exclude_domain)
    else:
        directory_path = ""
    full_directory_path = current_directory + directory_path

    if not os.path.exists(full_directory_path):
        os.makedirs(full_directory_path)
    file = open(full_directory_path + directory_file, "wb")
    sizeReceived = 1024
    header = receiveHeader(s)

    return s, file, sizeReceived, header

# change extension file to new kind
def changeExtensionToNewKind(directory_file, tempFile, new_kind):
    if os.path.exists(tempFile):
        os.remove(tempFile)
    p = Path(directory_file)
    p.rename(p.with_suffix(new_kind))

# check if link has subfolder
def checkIfSubFolder(directory_file, link):
    if '.' in link.rsplit('/')[0]:
        return False
    if ".html" not in directory_file:
        return False

    tempFile = directory_file.replace(".html", ".txt")
    changeExtensionToNewKind(directory_file, tempFile, ".txt")

    f = open(tempFile, "r")

    isHasTableTab = False
    isHasHref = False
    for line in f:
        if "href=" in line:
            isHasHref = True
        if "table" in line:
            isHasTableTab = True

    f.close()

    changeExtensionToNewKind(tempFile, directory_file, ".html")

    return isHasTableTab and isHasHref

# get directory files in rootfile .txt
def downloadDirectoryFiles(directory_file, domain, link_exclude_domain):
    tempFile = directory_file.replace(".html", ".txt")
    changeExtensionToNewKind(directory_file, tempFile, ".txt")

    f = open(tempFile, "r")
    
    for line in f:
        if "href=" not in line:
            continue
        if "?C=N;O=D" in line:
            continue
        restLink = line.split("href=\"")[1].split("\"")[0]
        directory_subfile = line.split(restLink + "\">")[1].split("</a>")[0]
        
        s, file, sizeReceived, header = prepareToConnect(link_exclude_domain + restLink, domain, directory_subfile, True)
        if(b"Content-Length" in header):
            contentLength = getContentLength(header)
            connectContentLength(s, file, sizeReceived, contentLength)
        elif(b"Transfer-Encoding: chunked" in header):
            connectChunked(s, file, sizeReceived)

    f.close()
    changeExtensionToNewKind(tempFile, directory_file, ".html")

# client socket
def clientSocket(link):
    file_name, domain, link_exclude_domain, directory_file = analyzeLink(link)
    s, file, sizeReceived, header = prepareToConnect(link_exclude_domain, domain, directory_file, False)

    if(b"Content-Length" in header):
        contentLength = getContentLength(header)
        connectContentLength(s, file, sizeReceived, contentLength)
    elif(b"Transfer-Encoding: chunked" in header):
        connectChunked(s, file, sizeReceived)

    file.close()
    s.close()

    if checkIfSubFolder(directory_file, link):
        downloadDirectoryFiles(directory_file, domain, link_exclude_domain)

if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor() as executor:
        for index in range(1, len(sys.argv)):
            link = sys.argv[index]
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            executor.submit(clientSocket, link)