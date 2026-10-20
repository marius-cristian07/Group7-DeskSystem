1. Start the simulator
	Fisrt open the terminal in the root Group7-DeskSystem folder and run the following commands: <br/>
	
	git submodule update --init --recursive (Only needs to run the first time) <br/>

	cd wifi2ble-box-simulator <br/>
	python simulator/main.py --port 8000

2. Get an API key <br/>
	Group7-DeskSystem\wifi2ble-box-simulator\config\api_keys.json <br/>
	They are in the file above copy any of the 2 keys

3. List all desks <br/>
	http://localhost:8000/api/v2/<api_key>/desks
	 
	Paste the link above in your browser and replace <api_key> with the key you copied in step 2. You should see a list of all desks. 

4. Get one desk <br/>
	http://localhost:8000/api/v2/<api_key>/desks/<desk_id> <br/>

	Paste the link above in your browser and replace <api_key> with the key you copied in step 2 and <desk_id> with the id of the desk you want to get form the list.

5. The server can also be started in HTTPS mode <br/>
   python simulator/main.py --port 8443 --https --certfile config/cert.pem --keyfile config/key.pem

   Ex with port 8443

