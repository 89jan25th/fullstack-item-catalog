from flask import Flask, render_template
from flask import request, redirect, jsonify, url_for, flash
from sqlalchemy import create_engine, asc
from sqlalchemy.orm import sessionmaker, scoped_session
from database_setup import Base, Hospital, Service, User
from flask import session as login_session
import random
import string
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests

app = Flask(__name__)

CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Clinical Service List Application"


# Connect to Database and create database session
engine = create_engine('sqlite:///hospital.db')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = scoped_session(DBSession)


# Create anti-forgery state token
@app.route('/login/')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    # return "The current session state is %s" % login_session['state']
    return render_template('login.html', STATE=state)


@app.route('/fbconnect', methods=['POST'])
def fbconnect():
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    access_token = request.data
    print "access token received %s " % access_token

    app_id = json.loads(open('fb_client_secrets.json', 'r').read())[
        'web']['app_id']
    app_secret = json.loads(
        open('fb_client_secrets.json', 'r').read())['web']['app_secret']
    url = 'https://graph.facebook.com/oauth/access_token?grant_type=\
    fb_exchange_token&client_id=%s&client_secret=%s&fb_exchange_token=%s' % (
        app_id, app_secret, access_token)
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]

    # Use token to get user info from API
    userinfo_url = "https://graph.facebook.com/v2.8/me"

    token = result.split(',')[0].split(':')[1].replace('"', '')

    url = 'https://graph.facebook.com/v2.8/me?access_token=\
    %s&fields=name,id,email' % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    # print "url sent for API access:%s"% url
    # print "API JSON result: %s" % result
    data = json.loads(result)
    login_session['provider'] = 'facebook'
    login_session['username'] = data["name"]
    login_session['email'] = data["email"]
    login_session['facebook_id'] = data["id"]

    # The token must be stored in the login_session in order to properly logout
    login_session['access_token'] = token

    # Get user picture
    url = 'https://graph.facebook.com/v2.8/me/picture?\
    access_token=%s&redirect=0&height=200&width=200' % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    data = json.loads(result)

    login_session['picture'] = data["data"]["url"]

    # see if user exists
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']

    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: \
    150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '

    flash("Now logged in as %s" % login_session['username'])
    return output


@app.route('/fbdisconnect/')
def fbdisconnect():
    facebook_id = login_session['facebook_id']
    # The access token must me included to successfully logout
    access_token = login_session['access_token']
    url = 'https://graph.facebook.com/%s/\
    permissions?access_token=%s' % (facebook_id, access_token)
    h = httplib2.Http()
    result = h.request(url, 'DELETE')[1]
    return "you have been logged out"


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('Current \
            user is already connected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']
    # ADD PROVIDER TO LOGIN SESSION
    login_session['provider'] = 'google'

    # see if user exists, if it doesn't make a new one
    user_id = getUserID(data["email"])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: \
    150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
    flash("you are now logged in as %s" % login_session['username'])
    print "done!"
    return output

# User Helper Functions


def createUser(login_session):
    newUser = User(name=login_session['username'], email=login_session[
                   'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except BaseException:
        return None

# DISCONNECT - Revoke a current user's token and reset their login_session


@app.route('/gdisconnect/')
def gdisconnect():
    # Only disconnect a connected user.
    access_token = login_session.get('access_token')
    if access_token is None:
        response = make_response(
            json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    if result['status'] == '200':
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        response = make_response(json.dumps('Failed \
            to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response


# JSON APIs to view hospital Information
@app.route('/hospital/<int:hospital_id>/service/JSON')
def hospitalServiceJSON(hospital_id):
    hospital = session.query(Hospital).filter_by(id=hospital_id).one()
    services = session.query(Service).filter_by(
        hospital_id=hospital_id).all()
    return jsonify(services=[i.serialize for i in services])


@app.route('/hospital/<int:hospital_id>/service/<int:service_id>/JSON')
def serviceJSON(hospital_id, service_id):
    services = session.query(Service).filter_by(id=service_id).one()
    return jsonify(services=services_Item.serialize)


@app.route('/hospital/JSON')
def hospitalsJSON():
    hospitals = session.query(Hospital).all()
    return jsonify(hospitals=[r.serialize for r in hospitals])


# Show all hospitals
@app.route('/')
@app.route('/hospital/')
def showhospital():
    hospital = session.query(Hospital).order_by(asc(Hospital.name))
    if 'username' not in login_session:
        return render_template('publichospitals.html', hospital=hospital)
    else:
        return render_template('hospitals.html', hospital=hospital)

# Create a new hospital


@app.route('/hospital/new/', methods=['GET', 'POST'])
def newhospital():
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        newhospital = Hospital(
            name=request.form['name'],
            user_id=login_session['user_id'],
            location=request.form['location'],
            description=request.form['description'],
            rating=request.form['rating'])
        session.add(newhospital)
        flash('New hospital %s Successfully Created' % newhospital.name)
        session.commit()
        return redirect(url_for('showhospital'))
    else:
        return render_template('newhospital.html')

# Edit a hospital


@app.route('/hospital/<int:hospital_id>/edit/', methods=['GET', 'POST'])
def edithospital(hospital_id):
    editedhospital = session.query(
        Hospital).filter_by(id=hospital_id).one()
    if 'username' not in login_session:
        return redirect('/login')
    if editedhospital.user_id != login_session['user_id']:
        return "<script>function myFunction() {alert('You are \
        not authorized to edit this hospital. Please create your \
        own hospital in order to edit.');}\
        </script><body onload='myFunction()'>"
    if request.method == 'POST':
        if request.form['name']:
            editedhospital.name = request.form['name']
        if request.form['location']:
            editedhospital.location = request.form['location']
        if request.form['description']:
            editedhospital.description = request.form['description']
        if request.form['rating']:
            editedhospital.description = request.form['rating']
        flash('hospital Successfully Edited %s' % editedhospital.name)
        return redirect(url_for('showhospital'))
    else:
        return render_template('edithospital.html', hospital=editedhospital)


# Delete a hospital
@app.route('/hospital/<int:hospital_id>/delete/', methods=['GET', 'POST'])
def deletehospital(hospital_id):
    hospitalToDelete = session.query(
        Hospital).filter_by(id=hospital_id).one()
    if 'username' not in login_session:
        return redirect('/login')
    if hospitalToDelete.user_id != login_session['user_id']:
        return "<script>function myFunction() \
        {alert('You are not authorized to delete this hospital. \
        Please create your own hospital in order to delete.');}\
        </script><body onload='myFunction()'>"
    if request.method == 'POST':
        servicesToDelete = session.query(Service).\
            filter_by(hospital_id=hospital_id).all()
        for serviceToDelete in servicesToDelete:
            session.delete(serviceToDelete)
            session.commit()
        session.delete(hospitalToDelete)
        temp = hospitalToDelete.name
        session.commit()

        flash('%s Successfully Deleted' % temp)
        return redirect(url_for('showhospital', hospital_id=hospital_id))
    else:
        return render_template('deletehospital.html',
                               hospital=hospitalToDelete)

# Show a hospital service


@app.route('/hospital/<int:hospital_id>/')
@app.route('/hospital/<int:hospital_id>/service/')
def showservice(hospital_id):
    hospital = session.query(Hospital).filter_by(id=hospital_id).one()
    creator = getUserInfo(hospital.user_id)
    items = session.query(Service).filter_by(
        hospital_id=hospital_id).all()
    if 'username' not in login_session or creator.id != login_session['user_id']:
        return render_template('publicservice.html',
                               items=items,
                               hospital=hospital,
                               creator=creator)
    else:
        return render_template('service.html',
                               items=items,
                               hospital=hospital,
                               creator=creator)


# Create a new service item
@app.route('/hospital/<int:hospital_id>/service/new/', methods=['GET', 'POST'])
def newserviceItem(hospital_id):
    if 'username' not in login_session:
        return redirect('/login')
    hospital = session.query(Hospital).filter_by(id=hospital_id).one()
    if login_session['user_id'] != hospital.user_id:
        return "<script>function myFunction() \
        {alert('You are not authorized to add service \
        items to this hospital. Please create your own \
        hospital in order to add items.');}</script><body \
        onload='myFunction()'>"
    if request.method == 'POST':
        newService = Service(name=request.form['name'],
                             description=request.form['description'],
                             price=request.form['price'],
                             recovery_weeks=request.form['recovery_weeks'],
                             hospital_id=hospital_id,
                             user_id=hospital.user_id)
        session.add(newService)
        session.commit()
        flash('New service %s Item Successfully Created' % (newService.name))
        return redirect(url_for('showservice', hospital_id=hospital_id))
    else:
        return render_template('newService.html', hospital_id=hospital_id)

# Edit a service item


@app.route('/hospital/<int:hospital_id>/service/<int:service_id>/edit/',
           methods=['GET', 'POST'])
def editserviceItem(hospital_id, service_id):
    if 'username' not in login_session:
        return redirect('/login')
    editedItem = session.query(Service).filter_by(id=service_id).one()
    hospital = session.query(Hospital).filter_by(id=hospital_id).one()
    if login_session['user_id'] != hospital.user_id:
        return "<script>function myFunction()\
         {alert('You are not authorized to edit service \
         items to this hospital. Please create your own \
         hospital in order to edit items.');}</script><body \
         onload='myFunction()'>"
    if request.method == 'POST':
        if request.form['name']:
            editedItem.name = request.form['name']
        if request.form['description']:
            editedItem.description = request.form['description']
        if request.form['price']:
            editedItem.price = request.form['price']
        if request.form['course']:
            editedItem.course = request.form['course']
        session.add(editedItem)
        session.commit()
        flash('service Item Successfully Edited')
        return redirect(url_for('showservice', hospital_id=hospital_id))
    else:
        return render_template('editservice.html',
                               hospital_id=hospital_id,
                               service_id=service_id,
                               item=editedItem)


# Delete a service item
@app.route('/hospital/<int:hospital_id>/service/<int:service_id>/delete/',
           methods=['GET', 'POST'])
def deleteserviceItem(hospital_id, service_id):
    if 'username' not in login_session:
        return redirect('/login')
    hospital = session.query(Hospital).filter_by(id=hospital_id).one()
    itemToDelete = session.query(Service).filter_by(id=service_id).one()
    if login_session['user_id'] != hospital.user_id:
        return "<script>function myFunction() {alert('You \
        are not authorized to delete service items to this \
        hospital. Please create your own hospital in order \
        to delete items.');}</script><body onload='myFunction()'>"
    if request.method == 'POST':
        session.delete(itemToDelete)
        session.commit()
        flash('service Item Successfully Deleted')
        return redirect(url_for('showservice', hospital_id=hospital_id))
    else:
        return render_template('deleteService.html', item=itemToDelete)

# Disconnect based on provider
@app.route('/disconnect/')
def disconnect():
    if 'provider' in login_session:
        if login_session['provider'] == 'google':
            gdisconnect()
            del login_session['gplus_id']
            del login_session['access_token']
        if login_session['provider'] == 'facebook':
            fbdisconnect()
            del login_session['facebook_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        del login_session['user_id']
        del login_session['provider']
        flash("You have successfully been logged out.")
        return redirect(url_for('showhospital'))
    else:
        flash("You were not logged in")
        return redirect(url_for('showhospital'))


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
