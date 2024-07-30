# ------------------------------------------------------------------------------------------ #
# Title: Assignment05
# Desc: This assignment demonstrates using dictionaries, files, and exception handling
# Change Log: (Who, When, What)
#   NPlaza,7/25/2024,Created Script
#   NPlaza,7/26/2024,Functions 1 and 3
#   NPlaza,7/28/2024,Function 2
#   NPlaza,7/29/2024,Final Debug + exception handling
# ------------------------------------------------------------------------------------------ #
import json

# Define the Data Constants
MENU: str = '''
---- Course Registration Program ----
  Select from the following menu:  
    1. Register a Student for a Course.
    2. Show current data.  
    3. Save data to a file.
    4. Exit the program.
----------------------------------------- 
'''
FILE_NAME: str = "Enrollments.json"

# Define the Data Variables and constants
student_first_name: str = ''  # Holds the first name of a student entered by the user.
student_last_name: str = ''  # Holds the last name of a student entered by the user.
course_name: str = ''  # Holds the name of a course entered by the user.
json_data: str = ''  # Holds combined string data separated by a comma.
file = None  # Holds a reference to an opened file.
menu_choice: str = ''  # Hold the choice made by the user.
student_data: dict = {}  # one row of student data
students: list = []  # a table of student data

# When the program starts, read the file data into a list of dictionaries (table)
try:
    with open(FILE_NAME, "r") as file:
        students = json.load(file)
except FileNotFoundError:
    print("File not found. A new file will be created upon saving.")
except json.JSONDecodeError:
    print("File is empty or contains invalid JSON. A new file will be created upon saving.")
except Exception as e:
    print("There was a non-specific error!")
    print("-- Technical Error Message --")
    print(e, e.__doc__, type(e), sep='\n')

# Present and Process the data
while True:
    # Present the menu of choices
    print(MENU)
    menu_choice = input("What would you like to do: ")

    # Input user data
    if menu_choice == "1":
        # Input the data
        student_first_name = input("What is the student's first name? ")
        student_last_name = input("What is the student's last name? ")
        course_name = input("Please enter the name of the course: ")
        student_data = {"FirstName": student_first_name, "LastName": student_last_name, "CourseName": course_name}
        students.append(student_data)

    # Present the current data
    elif menu_choice == "2":
        print("\n--- Displaying data ---")
        for row in students:
            print(f'{row["FirstName"]}, {row["LastName"]}, {row["CourseName"]}')
        print("=" * 30)

    # Save the data to a file
    elif menu_choice == "3":
        try:
            with open(FILE_NAME, "w") as file:
                json.dump(students, file, indent=4)
            print(f"Data has been saved to {FILE_NAME}")
        except Exception as e:
            print("There was an error saving to the file!")
            print("-- Technical Error Message --")
            print(e, e.__doc__, type(e), sep='\n')

    # Stop the loop
    elif menu_choice == "4":
        break  # out of the loop
    else:
        print("Please only choose option 1, 2, 3, or 4")

print("Program Ended")
