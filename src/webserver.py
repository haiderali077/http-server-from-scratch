'''
Currently, this web server handles only one HTTP request at a time which in
practice is not efficient for handling multiple connections but it gives us a
starting point for looking at the HTTP protocol.
'''

# Import socket module
from socket import *

import sys                                  # In order to terminate the program
import getopt                               # for processsing of args from cmd
import os                                   # file API <-allows you to acess
                                            # the file system
import re                                   # regular expression library
                                            # <- handy for string processing
from datetime import datetime, timedelta    # for managing times - Handy things


def get_content_type(filename):
    # check extension so we can send the right type to browser
      if filename.endswith(".html") or filename.endswith(".htm"):
          return "text/html"
      elif filename.endswith(".css"):
          return "text/css"
      elif filename.endswith(".js"):
          return "application/javascript"
      elif filename.endswith(".json"):
          return "application/json"
      elif filename.endswith(".png"):
          return "image/png"
      elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
          return "image/jpeg"
      elif filename.endswith(".gif"):
          return "image/gif"
      elif filename.endswith(".ico"):
          return "image/x-icon"
      elif filename.endswith(".pdf"):
          return "application/pdf"
      else:
          return "application/octet-stream"   # for others just send like generic data


def format_http_date(timestamp=None):
    # format the time into HTTP readable format like Sat, 05 Oct 2025 12:00:00 GMT
      if timestamp is None:
          timestamp = datetime.utcnow()
      else:
          timestamp = datetime.utcfromtimestamp(timestamp)
      return timestamp.strftime("%a, %d %b %Y %H:%M:%S GMT")


def main(argv):

    serverPort = 6789

    # Get the port number at start up, but will default to 6789
    try:
        opts, args = getopt.getopt(argv,"hp:",["port="])
    except getopt.GetoptError:
        print ('webserver.py -p <port number>')
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print('webserver.py -p <port number>')
            sys.exit()
        elif opt in ("-p", "--port"):
            serverPort = int(arg)

    print('Server is running on port ', serverPort)

    # Create a TCP server socket
    # (AF_INET is used for IPv4 protocols)
    # (SOCK_STREAM is used for TCP)
    # This sets up a TCP sockect
    serverSocket = socket(AF_INET, SOCK_STREAM)

    # Bind the socket to server address and server port
    serverSocket.bind(("", serverPort))

    # Listen to at most 1 connection at a time
    serverSocket.listen(1)

    # Server should be up and running and listening to the incoming connections
    # keep looping forever
    while True:
        print('The server is ready to receive data....')

        # Set up a new connection from the client
        connectionSocket, addr = serverSocket.accept()

        try:
            # Receives the request message from the clientself.
            # It will wait until data has been recieved from client
            # The decode(encoding='UTF-8') ensurse that the data is interpreted
            # as ASCII
            message = connectionSocket.recv(1024).decode(encoding='UTF-8')
            # print the HTTP request type of message - for diagnoistics
            print(message)  # this should print out what was received from the
                            # client

            responseHeader = ""       # this is your empty response
            # Start your coding here!!

            # parse the first line and get method and path
            lines = message.split('\r\n')
            if not lines:
                connectionSocket.close()
                continue
            
            parts = lines[0].split()
            if len(parts) < 2:
                connectionSocket.close()
                continue
            method = parts[0]
            path = parts[1]
            
            # parse headers for conditional GET
            if_modified_since = None
            for line in lines[1:]:
                if line.lower().startswith('if-modified-since:'):
                    if_modified_since = line.split(':', 1)[1].strip()
                    break

            # only GET is allowed, other methods not allowed so we send 405
            if method != "GET":
                msg = "<html><body><h1>405 Method Not Allowed</h1></body></html>"
                responseHeader = "HTTP/1.1 405 Method Not Allowed\r\n"
                responseHeader += "Allow: GET\r\n"
                responseHeader += f"Date: {format_http_date()}\r\n"
                responseHeader += "Server: SimplePythonServer/1.0\r\n"
                responseHeader += f"Content-Length: {len(msg)}\r\n"
                responseHeader += "Content-Type: text/html\r\n"
                responseHeader += "Connection: close\r\n\r\n"
                connectionSocket.send(responseHeader.encode())
                connectionSocket.send(msg.encode())
                connectionSocket.close()
                continue

            # handle root request when no file given
            if path == "/" or path == "":
                  filename = "index.html"
            else:
                  filename = path.lstrip("/")  # remove / from start

            # if path end with / means a folder so we look for index.html inside it
            if filename.endswith("/"):
                filename += "index.html"

            # if file has no ext then we assume .html
            if not re.search(r'\.[a-zA-Z]+$', filename):
                if os.path.isdir(filename):
                    filename = os.path.join(filename, "index.html")
                else:
                    if os.path.exists(filename + ".html"):
                        filename += ".html"
                    elif os.path.exists(filename + ".htm"):
                        filename += ".htm"
                    else:
                        filename += ".html"

            # remove dangerous .. things from path
            if ".." in filename:
                filename = filename.replace("..", "")

            # first check if media type is supported before checking if file exists
            # but only if the filename has an extension
            ext = os.path.splitext(filename)[1].lower()
            if ext:  # only check if there's an extension
                supported_text = ['.html', '.htm', '.css', '.js', '.json']
                supported_binary = ['.png', '.jpg', '.jpeg', '.gif', '.ico', '.pdf']
                supported_media = supported_text + supported_binary

                if ext not in supported_media:
                      # file type not allowed so send 415
                      msg = "<html><body><h1>415 Unsupported Media Type</h1></body></html>"
                      responseHeader = "HTTP/1.1 415 Unsupported Media Type\r\n"
                      responseHeader += f"Date: {format_http_date()}\r\n"
                      responseHeader += "Server: SimplePythonServer/1.0\r\n"
                      responseHeader += f"Content-Length: {len(msg)}\r\n"
                      responseHeader += "Content-Type: text/html\r\n"
                      responseHeader += "Connection: close\r\n\r\n"
                      connectionSocket.send(responseHeader.encode())
                      connectionSocket.send(msg.encode())
                      connectionSocket.close()
                      continue
            else:
                # if no extension, set supported lists for later use
                supported_text = ['.html', '.htm', '.css', '.js', '.json']
                supported_binary = ['.png', '.jpg', '.jpeg', '.gif', '.ico', '.pdf']

            # if file not found we return 404 page
            if not os.path.exists(filename):
                  errorBody = "<html><body><h1>404 Not Found</h1></body></html>"
                  responseHeader = "HTTP/1.1 404 Not Found\r\n"
                  responseHeader += f"Date: {format_http_date()}\r\n"
                  responseHeader += "Server: SimplePythonServer/1.0\r\n"
                  responseHeader += f"Content-Length: {len(errorBody)}\r\n"
                  responseHeader += "Content-Type: text/html\r\n"
                  responseHeader += "Connection: close\r\n\r\n"
                  connectionSocket.send(responseHeader.encode())
                  connectionSocket.send(errorBody.encode())
                  connectionSocket.close()
                  continue

            # get file info for last modified time
            lastModTime = os.path.getmtime(filename)
            lastMod = format_http_date(lastModTime)
            
            # check for conditional GET (If-Modified-Since header)
            if if_modified_since:
                try:
                    # parse the client's If-Modified-Since date
                    from datetime import datetime
                    client_date = datetime.strptime(if_modified_since, "%a, %d %b %Y %H:%M:%S %Z")
                    file_date = datetime.utcfromtimestamp(lastModTime)
                    
                    # if file hasn't been modified since client's date, return 304
                    if file_date <= client_date:
                        responseHeader = "HTTP/1.1 304 Not Modified\r\n"
                        responseHeader += f"Date: {format_http_date()}\r\n"
                        responseHeader += "Server: SimplePythonServer/1.0\r\n"
                        responseHeader += f"Last-Modified: {lastMod}\r\n"
                        responseHeader += "Connection: close\r\n\r\n"
                        connectionSocket.send(responseHeader.encode())
                        connectionSocket.close()
                        continue
                except:
                    # if date parsing fails, proceed with normal response
                    pass
            
            # now detect file type for content-type header
            mime = get_content_type(filename)
            ext = os.path.splitext(filename)[1].lower()

            # read the file in right mode for text or binary
            if ext in supported_binary:
                 with open(filename, "rb") as f:
                     body = f.read()
            else:
                 with open(filename, "r", encoding="utf-8") as f:
                     body = f.read().encode("utf-8")

            # get file info for size
            size = len(body)

            # build the 200 OK header
            responseHeader = "HTTP/1.1 200 OK\r\n"
            responseHeader += f"Date: {format_http_date()}\r\n"
            responseHeader += "Server: SimplePythonServer/1.0\r\n"
            responseHeader += f"Last-Modified: {lastMod}\r\n"
            responseHeader += f"Content-Type: {mime}\r\n"
            responseHeader += f"Content-Length: {size}\r\n"
            responseHeader += "Connection: close\r\n\r\n"

            # send the data back to browser
            connectionSocket.send(responseHeader.encode())
            connectionSocket.send(body)

            # after sending done close socket
            connectionSocket.close()

        except IOError:
                # Send HTTP response message for file not found
                # this will always need to be run, if a file can't be Found
                # assuming it is a valid type
                connectionSocket.send("HTTP/1.1 404 Not Found\r\n\r\n".encode(encoding='UTF-8'))
                connectionSocket.send("<html><head></head><body><h1>404 Not Found</h1></body></html>\r\n".encode(encoding='UTF-8'))
                # Close the client connection socket
                connectionSocket.close()


    serverSocket.close()
    # Terminate the program after sending the corresponding data
    sys.exit()

if __name__ == "__main__":
    main(sys.argv[1:])
