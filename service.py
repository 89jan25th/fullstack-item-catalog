from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database_setup import Base, Hospital, Service, User

engine = create_engine('sqlite:///hospital.db')
# Bind the engine to the metadata of the Base class so that the
# declaratives can be accessed through a DBSession instance
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
# A DBSession() instance establishes all conversations with the database
# and represents a "staging zone" for all the objects loaded into the
# database session object. Any change made against the objects in the
# session won't be persisted into the database until you call
# session.commit(). If you're not happy about the changes, you can
# revert all of them back to the last commit by calling
# session.rollback()
session = DBSession()


# Create dummy user
User1 = User(name="Robo Barista", email="tinnyTim@udacity.com",
             picture='https://pbs.twimg.com/profile_images/2671170543/18debd694829ed78203a5a36dd364160_400x400.png')
session.add(User1)
session.commit()

# service for Seoul Thyroid Expert Hospital
hospital1 = Hospital(user_id=1, name="Seoul Thyroid Expert Hospital", location="Seoul", description="Best kwnown for thyroid surguries", rating=2.5)

session.add(hospital1)
session.commit()

service1 = Service(user_id=1, name="thyroidectomy", description="removes all or part of the thyroid gland.",
                     price="$500", recovery_weeks=16, hospital=hospital1)

session.add(service1)
session.commit()


service2 = Service(user_id=1, name="lobectomy", description="removes one of the two lobes of the thyroid.",
                     price="$1000", recovery_weeks=16, hospital=hospital1)

session.add(service2)
session.commit()


# service for Gangnam Cosmetic Surgery Clinic
hospital2 = Hospital(user_id=1, name="Gangnam Cosmetic Surgery Clinic", location="Seoul", description="Celebrities' favourite place", rating=3.0)

session.add(hospital2)
session.commit()


service1 = Service(user_id=1, name="eyelift", description="reduces bagginess from lower eyelids and removes excess skin from the upper eyelids.",
                     price="$700", recovery_weeks=4, hospital=hospital2)

session.add(service1)
session.commit()

service2 = Service(user_id=1, name="Rhinoplasty Surgery",
                     description="changes the shape of the nose", price="$800", recovery_weeks=8, hospital=hospital2)

session.add(service2)
session.commit()


print "added service items!"
