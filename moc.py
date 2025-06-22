# MN Analysis of Sentencing Trends
# By Sidney D. Allen

# MOC Tables
# COL is the title of the digit
# INC is the list of codes included in this section
class MnOffenseCodes:

    CODES = {
        'A': [
            'Assault',  # Complete

            {
                'COL': 'Category',
                '1': '1st Deg. Assault (Felony)',
                '2': '2nd Deg. Assault (Felony)',
                '3': '3rd Deg. Assault (Felony)',
                '4': '4th Deg. Assault (Felony)',
                '5': '5th Deg. Assault (Misdemeanor)',
                '6': 'Use of Drugs to Injure/Facilitate Crime (Felony)',
                '7': 'Coercion (Felony)',
                '8': 'Coercion (Misdemeanor)',
                '9': 'Terroristic Threats/Threats of Violence',
                '0': 'Unknown',
                'A': '4th Deg. Assault (Gross Misdemeanor)',
                'B': '4th Deg. Assault Motivated by Bias (Felony)',
                'C': '4th Deg. Assault Motivated by Bias (Gross Misdemeanor)',
                'D': '5th Deg. Assault (Gross Misdemeanor)',
                'E': 'Injury Unborn in Commission of Crime (Felony)',
                'F': 'Great Bodily Harm Caused by Distribution of Drugs',
                'G': '5th Deg. Assault (Felony)',
                'H': '3rd Deg. Assault Unborn (Misdemeanor)',
                'J': 'Domestic Assault (Felony)',
                'K': 'Domestic Assault (Gross Misdemeanor)',
                'L': 'Domestic Assault (Misdemeanor)',
                'M': 'Harm Caused by Dog',
                'N': 'Domestic Assault by Strangulation',
                'O': 'Sexual Extortion with Contact',
                'P': 'Sexual Extortion with Penetration'},
            {
                'COL': 'Act',
                '1': 'Inflicts Great Bodily Harm',
                '2': 'Inflicts Substantial Bodily Harm',
                '3': 'Inflicts or Attempts Bodily Harm',
                '4': 'Fear of Bodily Harm with No Injury',
                '5': 'Threat to Inflict Bodily Harm',
                '6': 'Threat to Inflict Damage to Property',
                '7': 'Threat to Injure Business',
                '8': 'Threat to Expose Secret',
                '9': 'Threat to Make Criminal Charge',
                '0': 'Unknown / Not Applicable',
                'A': 'Distributes Schedule I or II Controlled Substance',
                'B': 'Threatens Crime of Violence',
                'C': 'Acts in Reckless Disregard of Rick of Causing Terror',
                'D': 'Causes or Attempts to Cause Terror in Another',
                'E': 'Assaults Minor - Past Pattern Child Abuse',
                'F': 'Use or Attempt to Use Deadly Force',
                'G': 'Throw / Transfer Bodily Fluids',
                'H': 'Threat to Report Immigration Status',
                'J': 'Threat to Disseminate Private Images',
                'K': 'Threat to Change Housing Status'
            },

            {
                'COL': 'Weapon Use',
                '1': 'Firearm (Possess Only)',
                '2': 'Firearm',
                '3': 'Knife / Cutting Instrument',
                '4': 'Other Dangerous Weapon / Weapon Type Unknown',
                '5': 'Hands, Fists, Feet, Etc.',
                '6': 'Explosives',
                '7': 'Replica Firearm',
                '8': 'B. B. Gun',
                '0': 'No Weapon'
            },

            {
                'COL': 'Victim',
                '1': 'Adult - Family',
                '2': 'Adult - Acquaintance',
                '3': 'Adult - Stranger',
                '4': 'Child - Family',
                '5': 'Child - Acquaintance',
                '6': 'Child - Stranger',
                '7': 'Police',
                '8': 'Public Official',
                '9': 'Unborn Child',
                '0': 'Unknown',
                'A': 'Firefighter',
                'B': 'Emergency Medical Personnel',
                'C': 'Correctional Employee',
                'D': 'Child Under Age 4',
                'E': 'School Official',
                'F': 'Vulnerable Adult',
                'G': 'Community Crime Prevention Group Member',
                'H': 'Probation Officer',
                'L': 'Secure Treatment Facility Personnel',
                'M': 'Animal Control Officers',
                'N': 'Reserve Officers',
                'O': 'Utility and Postal Service Employees and Contractors',
                'P': 'Transit Operator'
            }
        ],

        'B': [
            'Burglary',  # Complete

            {
                'COL': 'Degree',
                '1': '1st Degree (Felony)',
                '2': '2nd Degree (Felony)',
                '3': '3rd Degree (Felony)',
                '4': '4th Degree (Gross Misdemeanor)',
                '0': 'Unknown'
            },

            {
                'COL': 'Act',
                '1': 'Occupied Dwelling Forced Entry',
                '2': 'Occupied Dwelling No Forced Entry',
                '3': 'Unoccupied Dwelling Forced Entry',
                '4': 'Unoccupied Dwelling No Forced Entry',
                '5': 'Occupied Building Forced Entry',
                '6': 'Occupied Building No Forced Entry',
                '7': 'Unoccupied Building Forced Entry',
                '8': 'Unoccupied Building No Forced Entry',
                '9': 'Attempted Forced Entry-Dwelling',
                '0': 'Attempted Forced Entry-Building',
                'A': 'Enter Government Building',
                'B': 'Enter Religious Establishment',
                'C': 'Enter Historic Property',
                'D': 'Enter School Building'
            },

            {
                'COL': 'Time Of Day / Weapon Use',
                '1': 'Day - Firearm',
                '2': 'Day - Other Dangerous Weapon',
                '3': 'Day - No Weapon / Unknown',
                '4': 'Night - Firearm',
                '5': 'Night - Other Dangerous Weapon',
                '6': 'Night - No Weapon / Unknown',
                '7': 'Unknown - Firearm',
                '8': 'Unknown - Other Dangerous Weapon',
                '9': 'Unknown - No Weapon / Unknown'
            },

            {
                'COL': 'Act Upon Entry',
                '1': 'Commits Assault',
                '2': 'Commits Criminal Sexual Conduct',
                '3': 'Commits Other Person Offense',
                '4': 'Commits or Intend to Commit Theft',
                '5': 'Commits or Intend to Commit Other Property Offense',
                '6': 'Intend to Commit Assault',
                '7': 'Intend to Commit Criminal Sexual Conduct',
                '8': 'Intend to Commit Other Person Offense',
                '0': 'Unknown / Not Applicable'
            }
        ],

        'C': [
            'Forgery / Counterfeiting',  # Complete

            {
                'COL': 'Level',
                '1': 'Felony',
                '2': 'Gross Misdemeanor',
                '3': 'Misdemeanor',
                '0': 'Unknown'
            },

            {
                'COL': 'Act',
                '1': 'Make / Alter / Destroy',
                '2': 'Utter / Possess / Place',
                '3': 'Uses',
                '4': 'Reproduce',
                '7': 'Endorse',
                '9': 'Other',
                '0': 'Unknown / Not Applicable'
            },

            {
                'COL': 'Type',
                '1': 'Check (Amount Unknown)',
                '2': 'Instrument',
                '3': 'Document',
                '4': 'Money',
                '5': 'Membership Card',
                '6': 'Label Stamp',
                '7': 'Fraudulent Drivers\' Licenses / ID Cards',
                '9': 'Other',
                '0': 'Unknown',
                'A': 'Check-More Than $35,000',
                'B': 'Check-More Than $2,500',
                'C': 'Check-$201-$2,500 [Pre 8/1/99]',
                'D': 'Check-$200 Or Less and Previous Conviction [Pre 8/1/99]',
                'E': 'Check-$200 Or Less [Pre 8/1/99]',
                'F': 'Tokens, Checks, Swigs, Similar to Lawful Coin',
                'G': 'Check-$251-$2,500 [Pre 8/1/99]',
                'H': 'Check-$250 Or Less and Previous Conviction [Pre 8/1/99]',
                'J': 'Check-$250 Or Less [Pre 8/1/99]',
                'K': 'U.S. Currency or Securities'
            },

            {
                'COL': 'Victim',
                '1': 'Person',
                '2': 'Business',
                '3': 'Public Office',
                '4': 'Corporation',
                '5': 'Association',
                '9': 'Other',
                '0': 'Unknown'
            }
        ],

        'D': [
            'Drugs',  # Complete

            {
                'COL': 'Category',
                '7': 'Schedule V',
                '8': 'Marijuana - Small Amount (Petty Misdemeanour, Not in Motor Vehicle)',
                '9': 'Other',
                '0': 'Unknown',
                'A': 'Marijuana - Small Amount (In Motor Vehicle)',
                'B': 'Simulated Controlled Substance',
                'C': 'Drug Paraphernalia',
                'D': '1st Degree Controlled Substance Offense',
                'E': '2nd Degree Controlled Substance Offense',
                'F': '3rd Degree Controlled Substance Offense',
                'G': '4th Degree Controlled Substance Offense',
                'H': '5th Degree Controlled Substance Offense',
                'J': 'Possession of Substances with Intent to Manufacture Methamphetamine',
                'K': 'Tampering/Theft - Anhydrous Ammonia',
                'L': 'Methamphetamine-Related Crimes Involving Children and Vulnerable Adults',
                'M': 'Other Controlled Substance Offenses',
                'N': 'Medical Cannabis Offenses'
            },

            {
                'COL': 'Act',
                '1': 'Manufacture/Produce',
                '2': 'Sale',
                '3': 'Distribute',
                '4': 'Possession with Intent To Sell/Manufacture/Distribute',
                '5': 'Possession',
                '6': 'Procure',
                '7': 'Attempt to Fraudulently Procure',
                '8': 'Forged Prescription',
                '9': 'Other',
                '0': 'Unknown / Not Applicable',
                'A': 'Import Across State Borders',
                'B': 'Advertise',
                'C': 'Deliver to Person Under 18',
                'D': 'Attempt Manufacture of Methamphetamine',
                'E': 'Diversion of Medial Cannabis',
                'F': 'False Statements',
                'G': 'Submission of False Records',
                'H': 'Violation by Health Care Professional',
                'J': 'Gross Misdemeanour 5th Degree Possession'
            },

            {
                'COL': 'Type of Drug',
                '1': 'Heroin',
                '2': 'Opium or Derivative',
                '3': 'Synthetic Narcotic',
                '4': 'Marijuana (Hashish)',
                '5': 'Cocaine - Powder',
                '6': 'Hallucinogen',
                '7': 'Amphetamine',
                '8': 'Barbiturate',
                '9': 'Simulated',
                '0': 'Unknown / Not Applicable',
                'A': 'Cocaine Base/Crack',
                'B': 'Toxic Substances',
                'C': 'Methamphetamine',
                'D': 'Anhydrous Ammonia',
                'E': 'Salvia Divinorum',
                'F': 'Khat',
                'G': 'Synthetic Cannabinoids',
                'H': 'Controlled Substance Analog',
                'J': 'Medical Cannabis',
                'K': 'Kratom'
            },

            {
                'COL': 'Offense Characteristics',
                '1': 'Involved Sale to Minor',
                '2': 'Offender Possessed a Firearm',
                '3': 'Conspire with or Employ a Minor',
                '4': 'Offender Possessed Other Dangerous Weapon',
                '5': 'School Zone',
                '6': 'Park Zone',
                '7': 'Public Housing Zone',
                '8': 'Not Applicable',
                '9': 'Drug Treatment Facility',
                '0': 'Unknown',
                'A': 'Aggravated First Degree'
            }
        ],

        'E': [
            'Escape / Flight',  # Complete

            {
                'COL': 'Level',
                '1': 'Felony with Violence',
                '2': 'Felony',
                '3': 'Gross Misdemeanor with Violence',
                '4': 'Gross Misdemeanor',
                '5': 'Misdemeanor with Violence',
                '6': 'Misdemeanor',
                '0': 'Unknown'
            },

            {
                'COL': 'Act',
                '1': 'In Lawful Custody',
                '2': 'Transfers Material to Another to Aid Escape',
                '3': 'Permits One to Escape',
                '4': 'Fleeing Officer Results in Death',
                '5': 'Fleeing Officer Results in Great Bodily Harm',
                '6': 'Fleeing Officer Results in Substantial Bodily Harm',
                '7': 'Fleeing Officer',
                '8': 'Failure to Appear',
                '9': 'Aiding Offender to Avoid Arrest',
                '0': 'Unknown / NA',
                'A': 'Not Guilty - Mental Illness Commitment',
                'B': 'Aid Offender - Obstruct Investigation / Prosecution',
                'C': 'Court Commitment as Sexual Psychopath',
                'D': 'Extradition',
                'E': 'Aid Offender on Probation Supervised Release',
                'F': 'Taking Responsibility for Criminal Acts',
                'G': 'While on Release Status from Civil Commitment',

    },

            {
                'COL': 'Weapon Used',
                '1': 'Firearm (Possess Only)',
                '2': 'Firearm',
                '3': 'Knife / Cutting Instrument',
                '4': 'Other Dangerous Weapon',
                '5': 'Hands, Fists, Feet, Etc.',
                '6': 'Explosives',
                '7': 'None',
                '0': 'Unknown'
            },

            {
                'COL': 'Type of Custody',
                '1': 'Prison',
                '2': 'Local Jail',
                '3': 'Other Lawful Custody',
                '4': 'Hospital',
                '5': 'Security Hospital',
                '6': 'Electronic Monitoring',
                '7': 'Unknown / Not Applicable'
            }
        ],

        'F': [
            'Arson / Negligent Fires',  # Complete

            {
                'COL': 'Category',
                '1': 'Arson 1 (Felony)',
                '2': 'Arson 2 (Felony)',
                '3': 'Arson 3 (Felony)',
                '4': 'Arson 3 (Misdemeanor) [pre 8/1/98]',
                '5': 'Negligent Fires (Felony)',
                '6': 'Negligent Fires (Gross Misdemeanor)',
                '7': 'Negligent Fires (Misdemeanor)',
                '8': 'Negligent Fires (Unknown)',
                '0': 'Unknown / Not Applicable',
                'A': 'Wildfire Arson - Sets (Felony)',
                'B': 'Wildfire Arson - Possession Flammable (Gross Misdemeanor)',
                'C': 'Arson 4 (Gross Misdemeanor)',
                'D': 'Arson 5 (Misdemeanor)',
            },

            {
                'COL': 'Condition / Weapon',
                '1': 'Inhabited - No Weapon/Unknown',
                '2': 'Uninhabited - No Weapon/Unknown',
                '3': 'Inhabited - Firearm',
                '4': 'Uninhabited - Firearm',
                '5': 'Inhabited - Other Weapon',
                '6': 'Uninhabited - Other Weapon',
                '7': 'Great Bodily Harm',
                '8': 'Inhabited - Flammable',
                '9': 'Uninhabited - Flammable',
                '0': 'Unknown',
                'A': 'Bodily Harm'
            },

            {
                'COL': 'Type of Property',
                '1': 'Single Occupancy - Residential',
                '2': 'Other Residential',
                '3': 'Storage',
                '4': 'Business - Industrial/Manufacturing',
                '5': 'Business - Other Commercial',
                '6': 'Community/Public Building',
                '7': 'Other - Structures',
                '8': 'Motor Vehicles'
            },

            {
                'COL': 'Property Loss / Value',
                'A': '$1,000 or More [arson]',
                'B': '$300 - $999 [arson]',
                'C': '$299 or Less [arson or negligent fires]',
                'D': '$300 - $2499 [negligent fires]',
                'E': '$2,500 or More [negligent fires]',
                'F': 'None Specified [wildfire arson]',
                'G': 'Greater than 5 Dwellings / 500 Acres / $100,000 [wildfire arson]',
                'H': 'Greater than 100 Dwellings / 1,500 Acres / $250,000 [wildfire arson]',
                'J': 'Demonstrable Bodily Harm [wildfire arson]',
            }
        ],

        'G': [
            'Gambling',  # Complete

            {
                'COL': 'Level',
                '1': 'Felony',
                '2': 'Gross Misdemeanor',
                '3': 'Misdemeanor',
                '0': 'Unknown'
            },

            {
                'COL': 'Act',
                '1': 'Makes / Manufacture',
                '2': 'Sells / Transfers / Sets Up',
                '3': 'Disseminate',
                '4': 'Permit',
                '5': 'Maintain / Operate / Conduct',
                '6': 'Participate in Income / Collects Proceeds',
                '7': 'Record (Bookmaking)',
                '8': 'Possess',
                '9': 'Receive / Forward',
                '0': 'Other / Unknown',
                'A': 'Pays Compensation for Game Credits',
                'B': 'Alter / Counterfeit Ticket',
                'C': 'Presents Altered / Counterfeit Ticket',
                'D': 'Transfers Altered / Counterfeit Ticket',
                'E': 'Claim Lottery Prize by Fraud / Deceit / Misrepresent',
                'F': 'Obtain Access to Computer Data Base',
                'G': 'Makes False Statements',
                'H': 'Prohibited Acts-Sell Ticket to Under 18',
                'J': 'Prohibited Acts-Unauthorized Sales / Price',
                'K': 'Prohibited Acts-Lottery Retailers / Vendors',
                'M': 'Disseminate False Information-State Lottery',
                'N': 'Cheats in a Game',
                'P': 'Use or Possess Prohibited Devices',
                'Q': 'Counterfeit Chips or Tokens',
                'R': 'Manufacture / Provide Equipment / Devices for Illegal Activity',
                'S': 'Instructs Others on Illegal Activity',
                'T': 'Lawful Gambling Fraud'
            },

            {
                'COL': 'Type (Digit 1)',
                'INC': [3, 4],
                '01': 'Bet-Other',
                '02': 'Bet-Horse',
                '03': 'Bet-Off Track',
                '04': 'Lottery (Not State Lottery)',
                '05': 'Gambling Place',
                '06': 'Bucket Shop',
                '07': 'Gambling Device / Goods',
                '08': 'Facility for Conducting Lottery',
                '09': 'Influencing Races',
                '10': 'Tampering with Horses',
                '11': 'Sports',
                '12': 'State Lottery Ticket',
                '13': 'Pari-mutuel Ticket',
                '14': 'To State Racing Commission',
                '15': 'To State Lottery Director',
                '16': 'Other',
                '17': 'Video Game of Chance',
                '18': 'At Authorized Gambling Establishment',
                '19': 'Electronic Pull-Tabs',
                '20': 'Electronic Linked Bingo',
                '21': 'Raffle Boards',
                '99': 'Other',
                '00': 'Unknown'
            },

            {
                'COL': 'Type (Digit 2)',
                'INC': [3, 4]
            }
        ],

        'H': [
            'Homicide / Suicide',  # Complete

            {
                'COL': 'Category',
                '1': 'Murder 1',
                '2': 'Murder 2',
                '3': 'Murder 3',
                '4': 'Manslaughter 1',
                '5': 'Manslaughter 2',
                '6': 'Adulteration / Death',
                '7': 'Aiding Suicide',
                '8': 'Aiding Attempted Suicide',
                '9': 'Death Unborn Child In Commission Crime'
            },

            {
                'COL': 'Act',
                '1': 'While Committing Criminal Sexual Conduct 1 or Criminal Sexual Conduct 2',
                '2': 'While Committing Burglary',
                '3': 'While Committing Aggravated Robbery',
                '4': 'While Committing Kidnapping',
                '5': 'While Committing Arson 1 or Arson 2',
                '6': 'While Committing Escape from Custody',
                '7': 'While Committing Tempering with Witness 1',
                '8': 'While Committing Other Felony Offense (Not Listed Above)',
                '9': 'While Committing Gross Misdemeanor or Misdemeanor Offense',
                '0': 'Unknown',
                'A': 'While Committing Child Abuse with Past Pattern of Child Abuse',
                'B': 'While Committing Domestic Abuse with Past Pattern of Domestic Abuse',
                'C': 'Distribution of Schedule I or II Controlled Substance',
                'D': 'Distribution of Schedule III, IV, or V Controlled Substance',
                'E': 'While Inflicting Bodily Harm When Restrained Under an Order for Protection',
                'F': 'While Committing a Drive-By Shooting',
                'G': 'While Committing Crime to Further Terrorism',
                'H': 'Premeditated and with Intent'
            },

            {
                'COL': 'Weapon Use',
                '1': 'Firearm (Possess Only)',
                '2': 'Firearm',
                '3': 'Knife / Cutting Instrument',
                '4': 'Other Dangerous Weapon',
                '5': 'Hands, Fists, Feet, Etc.',
                '6': 'Explosives',
                '0': 'Unknown / Not Applicable'
            },

            {
                'COL': 'Victim',
                '1': 'Adult - Family',
                '2': 'Adult - Acquaintance',
                '3': 'Adult - Stranger',
                '4': 'Child - Family',
                '5': 'Child - Acquaintance',
                '6': 'Child - Stranger',
                '7': 'Police / Guard',
                '8': 'Public Official',
                '9': 'Unborn Child',
                '0': 'Unknown',
            }
        ],

        'I': [
            'Crime Against Family',  # Complete

            {
                'COL': 'Level',
                '1': 'Felony',
                '2': 'Gross Misdemeanor',
                '3': 'Misdemeanor',
                '0': 'Unknown'
            },

            {
                'COL': 'Act (Digit 1)',
                'INC': [2,3],
                '01': 'Leaving the State to Evade Establishment of Paternity',
                '02': 'Bigamy',
                '03': 'Adultery',
                '04': 'Non-Support of Spouse or Child',
                '05': 'Contributing to Delinquency of a Minor',
                '06': 'Neglecting A Child',
                '07': 'Malicious Punishment of a Child',
                '08': 'Drugs to Produce Miscarriage',
                '09': 'Concealing Birth',
                '10': 'Endangering A Child',
                '11': 'Endangerment by Firearm Access',
                '12': 'Failure to Report-Child\'s Health in Serious Danger',
                '13': 'Child Abuse/Neglect - Failure by Mandated Person to Report',
                '14': 'Criminal Abuse Vulnerable Adult',
                '15': 'Neglect Vulnerable Adult',
                '16': 'Maltreatment Vulnerable Adult - Failure by Mandated Person to Report',
                '17': 'Female Genital Mutilation',
                '18': 'Tattoos - Provide to Minor',
                '19': 'Putative Father Registry - False Information',
                '20': 'Deprivation of Vulnerable Adult',
                '21': 'Child Torture',
                '00': 'Unknown'
            },

            {
                'COL': 'Act (Digit 2)',
                'INC': [2,3]
            },

            {
                'COL': 'Victim Injury',
                '1': 'Great Bodily Harm',
                '2': 'Substantial Bodily Harm',
                '3': 'Permits Continuing Physical / Sexual Abuse',
                '4': 'Substantially Harms Child\'s Physical / Emotional / Mental Health',
                '5': 'Bodily Harm - Victim Under Age 4',
                '6': 'Death',
                '7': 'Bodily Harm',
                '8': 'Sexual Contact / Penetration',
                '9': 'Other',
                '0': 'Unknown',
                'A': 'Previous Conviction [malicious punishment]'
            }
        ],

        'J': [
            'Traffic / Accidents',  # Complete

            {
                'COL': 'Level',
                '1': 'Felony',
                '2': 'Gross Misdemeanor',
                '3': 'Misdemeanor',
                '4': 'Gross Misdemeanor - Child Endangerment',
                '5': 'Juvenile Petty Misdemeanor',
                '8': 'Adult Petty Misdemeanor',
                '0': 'Unknown',
                'A': 'First Degree DWI [pre 8/1/2002]',
                'B': 'Second Degree DWI [pre 8/1/2002]',
                'C': 'Third Degree DWI [pre 8/1/2002]',
                'D': 'First Degree DWI (Felony) [effective 8/1/2002]',
                'E': 'Second Degree DWI (Gross Misdemeanor) [effective 8/1/2002]',
                'F': 'Third Degree DWI (Gross Misdemeanor) [effective 8/1/2002]',
                'G': 'Third Degree DWI (Misdemeanor) [effective 8/1/2002]',
            },

            {
                'COL': 'Act',
                '3': 'Failure to Stop/Report Accident (Driver Caused)',
                '4': 'Failure to Stop/Report Accident (Not Driver Caused)',
                '5': 'Driving Under Influence of Alcohol',
                '6': 'Driving Under Influence of Controlled Substance',
                '7': 'Aggravated Violation',
                '8': 'Reckless Driving',
                '9': 'Other',
                '0': 'Unknown',
                'A': 'Grossly Negligent Manner',
                'B': 'Negligent Manner Under Influence of Alcohol',
                'C': 'Negligent Manner Under Influence Controlled Substance',
                'D': 'Negligent Manner Under Influence Alcohol / Controlled Substance',
                'E': 'Alcohol Concentration of .10 or More [pre 8/1/2005]',
                'F': 'Alcohol Concentration of .10 or More Within 2 Hours of Driving [pre 8/1/2005]',
                'G': 'Under Influence of Alcohol / Controlled Substance',
                'H': 'Under Influence of Chemical Compound / Hazardous / Intoxicating Substance',
                'J': 'With Alcohol Concentration .04 or More - Commercial Motor Vehicle',
                'K': 'With Alcohol Concentration .04 or More Within 2 Hours of Driving - Commercial Motor Vehicle',
                'M': 'Within 8 Hours of Consuming Alcohol / Controlled Substance',
                'N': 'Owner Permits Person Under the Influence of Alcohol / Controlled Substance to Operate',
                'P': 'Owner Permits Person With Physical/Mental Disability to Operate',
                'R': 'Refusal to Submit to Test',
                'S': 'Any Amount Schedule I or II Controlled Substance',
                'T': 'Underage Drinking and Driving',
                'U': 'With Alcohol Concentration of .16 or More [.20 pre 8/1/2015]',
                'V': 'Physical Evidence Present in the Body of any Alcohol',
                'W': 'Alcohol Concentration of .08 or More',
                'X': 'Alcohol Concentration of .08 or More Within 2 Hours of Driving',
                'Y': 'Result of Cited Defective Maintenance'
            },

            {
                'COL': 'Injury / Aggravating Factors',
                '1': 'Death [felony only]',
                '2': 'Great Bodily Harm [felony only]',
                '3': 'Substantial Bodily Harm [felony only]',
                '4': 'Death Unborn Child [felony only]',
                '6': 'Injury Unborn Child [felony only]',
                '5': 'Bodily Harm [gross misdemeanor only]',
                '7': 'Death - Prior Qualified Impaired Driving Incident',
                '0': 'Unknown',
                'A': 'Qualified Prior Impaired Driving Incident [dwi only]',
                'B': 'Alcohol Concentration of .16 or More [dwi only, .20 pre 8/1/2015]',
                'C': 'With Child Under Age of 16 in Vehicle [dwi only]',
                'D': 'Refusal to Submit to Test [dwi only]',
                'E': 'Previous Felony Conviction Under Specified Provisions of 609.21 [felony dwi only]'
            },

            {
                'COL': 'Vehicle',
                '1': 'Motor Vehicle',
                '2': 'Aircraft',
                '3': 'All-Terrain Vehicle',
                '4': 'Snowmobile',
                '5': 'Watercraft / Motorboat',
                '6': 'Commercial Motor Vehicle',
                '7': 'School/Head-Start Bus',
                '8': 'Off-Road Vehicle',
                '0': 'Unknown'
            }
        ],

        'K': [
            'Kidnapping / False Imprisonment',  # Complete

            {
                'COL': 'Category',
                '1': 'Kidnapping - Great Bodily Harm Not Released in Safe Place',
                '2': 'Kidnapping-Great Bodily Harm Released in Safe Place',
                '3': 'Kidnapping-Not Great Bodily Harm Not Released in Safe Place',
                '4': 'Kidnapping-Not Great Bodily Harm Released in Safe Place',
                '5': 'False Imprisonment',
                '6': 'Depriving Another of Custodial or Parental Rights - Felony',
                '7': 'Abduction / Marriage',
                '8': 'Kidnapping-Victim Under Age 16',
                '9': 'Depriving Another of Custodial or Parental Rights - Gross Misdemeanor',
                '0': 'Unknown'
            },

            {
                'COL': 'Act',
                '1': 'Ransom/Reward for Release Shield Hostage',
                '2': 'Facilitate Commission of a Felony',
                '3': 'Injured / Threatened / Terrorized',
                '4': 'Involuntary Servitude',
                '5': 'Intentionally Confine or Restrain',
                '6': 'Abused or Neglected',
                '7': 'Previous Similar Conviction',
                '8': 'Substantial Bodily Harm',
                '9': 'Financial/Legal Obligation',
                '0': 'Unknown',
                'A': 'Conceal Minor Child',
                'B': 'Unreasonable Restraint of Children',
                'C': 'Takes/Retains/Fails to Return Child',
                'D': 'Causes/Contributes to Child Being Runaway',
                'E': 'Resides with Child',
                'F': 'Cause/Contribute to Child Being Habitual Truant',
                'G': 'Unreasonable Restraint of Children Resulting in Demonstrable Bodily Harm'
            },

            {
                'COL': 'Weapon Used',
                '1': 'Firearm (Possess Only)',
                '2': 'Firearm',
                '3': 'Knife / Cutting Instrument',
                '4': 'Other Dangerous Weapon',
                '5': 'Hands, Fists, Feet, Etc.',
                '6': 'Explosives',
                '9': 'None',
                '0': 'Unknown / Not Applicable'
            },

            {
                'COL': 'Victim',
                '1': 'Adult - Family',
                '2': 'Adult - Acquaintance',
                '3': 'Adult - Stranger',
                '4': 'Child - Family',
                '5': 'Child - Acquaintance',
                '6': 'Child - Stranger',
                '7': 'Police / Guard',
                '8': 'Public Official',
                '0': 'Unknown'
            }
        ],

        'L': [
            'Criminal Sexual Conduct',  # Complete

            {
                'COL': 'Degree',
                '1': 'Criminal Sexual Conduct 1',
                '2': 'Criminal Sexual Conduct 1 With Dangerous Weapon',
                '3': 'Criminal Sexual Conduct 2',
                '4': 'Criminal Sexual Conduct 2 With Dangerous Weapon',
                '5': 'Criminal Sexual Conduct 3',
                '6': 'Criminal Sexual Conduct 3 With Dangerous Weapon',
                '7': 'Criminal Sexual Conduct 4',
                '8': 'Criminal Sexual Conduct 4 With Dangerous Weapon',
                '9': 'Incest',
                '0': 'Unknown',
                'A': 'Criminal Sexual Conduct 5 (Gross Misdemeanor)',
                'B': 'Criminal Sexual Conduct 5 With Dangerous Weapon (Gross Misdemeanor)',
                'C': 'Criminal Sexual Conduct 5 (Felony)',
                'D': 'Criminal Sexual Predatory Conduct'
            },

            {
                'COL': 'Act',
                '1': 'No Force',
                '2': 'Fear of Great Bodily Harm',
                '3': 'Force or Coercion',
                '4': 'Personal Injury',
                '5': 'Personal Injury with Force or Coercion',
                '6': 'With Accomplice Using Force or Coercion',
                '7': 'With Accomplice Using Dangerous Weapon',
                '8': 'Multiple Acts',
                '9': 'Attempted',
                '0': 'Unknown / Not Applicable',
                'A': 'Non-consensual Sexual Contact',
                'B': 'Sexual Contact-Victim Under Age 13 [1st Degree Offenses only]',
                'C': 'Lewd Exhibition-Presence of Minor Under 16',
                'D': 'Intentionally Touch Body or Clothing with Semen',
                'E': 'Non-consensual Sexual Penetration',
                'F': 'Force With Bodily Harm Inflicted [1st & 2nd degree offenses only]'
            },

            {
                'COL': 'Assailant',
                '1': 'Spouse or Cohabiting Adult',
                '2': 'Natural Parent',
                '3': 'Guardian/Stepparent',
                '4': 'Other Family',
                '5': 'Person in Position of Authority',
                '6': 'Psychotherapist',
                '7': 'Acquaintance',
                '8': 'Stranger',
                '9': 'Health Care Professional',
                '0': 'Unknown / Not Applicable',
                'A': 'Clergy',
                'B': 'Correctional System Employee',
                'C': 'Special Transportation Service Employee',
                'D': 'Massage Therapists',
                'E': 'Secure Treatment Facility Personnel',
                'F': 'Licensed Peace Officer',
                'G': 'Educator / School Employee',
                'H': 'Personal Caregiver'
            },

            {
                'COL': 'Victim',
                '1': 'Under 13 Years Old/Female',
                '2': 'Under 13 Years Old/Male',
                '3': '13-15 Years Old/Female',
                '4': '13-15 Years Old/Male',
                '5': '16-17 Years Old/Female',
                '6': ' 16-17 Years Old/Male',
                '7': '18 or Older/Female',
                '8': '18 or Older/Male',
                '9': 'Unknown/Female',
                '0': 'Unknown/Male',
                'A': 'Under 14 Years Old/Female [effective 9-15-21]',
                'B': 'Under 14 Years Old / Male [effective 9-15-21]',
                'C': '14 - 15 Years Old / Female [effective 9-15-21]',
                'D': '14 - 15 Years Old / Male [effective 9-15-21]',
                'E': 'Vulnerable Adult [effective 9-15-21]'
            }
        ],

        'M': [
            'Miscellaneous / Federal / Conservation / Juvenile / Status / Liquor',  # Complete

            {
                'COL': 'Misc (Digit 1)',
                'INC': [1,2,3,4],
                '2206': 'Possession Of Burglary Tools (No Act Of Burglary Committed)',
                '0103': 'Espionage',
                '4101': 'Liquor – Manufacturing',
                '2207': 'Possession Code Grabbing Device',
                '0104': 'Sabotage',
                '4102': 'Liquor – Selling',
                '6099': 'Antitrust',
                '0105': 'Sedition',
                '4103': 'Liquor – Transporting',
                '7099': 'Other - Crimes Against Person',
                '0106': 'Selective Service',
                '4104': 'Liquor – Possessing',
                '7199': 'Other - Crimes Against Property',
                '0199': 'Sovereignty - Other',
                '4105': 'Misrepresenting Age (Minor)',
                '7299': 'Other - Crimes Agnst. Morals/Decency',
                '0301': 'Illegal Entry',
                '4106': 'Procuring Liquor For A Minor - Gross Misdemeanor',
                '7399': 'Other - Crimes Against Public Order',
                '0302': 'False Citizenship',
                '4113': 'Procuring Liquor For A Minor - Misdemeanor',
                '7401': 'Sale Of Tobacco/ Nicotine Delivery Devices To Children – Misdemeanor',
                '0303': 'Smuggling Aliens',
                '4107': 'Possession On School Grounds',
                '7402': 'Sale of Tobacco/Nicotine Delivery Devices To Children – Gross Misdemeanor',
                '0399': 'Immigration - Other',
                '4108': 'Sales To Minor Resulting In Death Or Great Bodily Harm',
                '7501': 'Hitchhiking',
                '1009': 'Hijack Aircraft',
                '4109': 'Sell/Distribute Poisonous Alcohol Or Other Alcohol Capable Of Causing Physical Or Mental Injuries',
                '7601': 'Adulteration Of Human Use Products Resulting In Illness, Pain Or Other Bodily Harm',
                '7602': 'Adulteration Of Human Use Products Not Resulting In Illness, Pain Or Other Bodily Harm',
                '2313': 'Obstruct Correspondence-Postal',
                '4110': 'Distribute Within 1,000 Feet Of A Prohibited Institution',
                '2603': 'Mail Fraud',
                '4111': 'Sell to Obviously Intoxicated Person',
                '2608': 'Fraud - Wire',
                '4112': 'Days/Hours Of Sale',
                '7701': 'Falsely Impersonating Another',
                '7801': 'Buy/Sell/Use Human Organs',
                '7901': 'Attempted Coercion',
                '2705': 'Embezzlement – Postal',
                '4120': 'Liquor Prohibited Acts',
                '4006': 'Transporting Females Interstate For Immoral Purposes',
                '4130': 'Intoxicating Liquor Licenses – Prohibited Acts',
                '4140': 'Underage Consumption - Age 18-21',
                '8001': 'Mistreatment of Persons Confined',
                '5009': 'Contempt Of Congress',
                '4199': 'Liquor – Other',
                '8002': 'Mistreatment of Residents-Patients',
                '5301': 'Anarchism',
                '8003': 'Living Will',
                '8101': 'Cruelty To Animals – Fights',
                '8102': 'Attend Animal Fight',
                '8180': 'Harm to Service Animal by Dog',
                '8181': 'Misrepresenting Service Animal',
                '8196': 'Mistreating Animals – Felony',
                '8197': 'Mistreating Animals – Gross Misdemeanor',
                '8198': 'Mistreating Animals – Misdemeanor',
                '8199': 'Cruelty To Animals – Other',
                '8201': 'Unauthorized Release Of Animals',
                '8202': 'False Traffic Signal',
                '8203': 'Discharge Laser at an Aircraft',
                '8301': 'Felony For Benefit Of Gang',
                '3001': 'Under Age Consumption - Under 18 (Juvenile Alcohol Offender)',
                '8302': 'Gross Misd. For Benefit Of Gang',
                '8303': 'Misdemeanor For Benefit Of Gang',
                '8401': 'Itinerant Carnivals',
                '8501': 'Prize Notices and Solicitations',
                '8304': 'Crime In Furtherance of Terrorism',
                '8601': 'Athlete Agents',
                '8603': 'Labor Trafficking',
                '8604': 'Unlawful Conduct-Documents - Labor or Sex Trafficking',
                '8605': 'False Material Information / Peacetime Emergency',
                '8606': 'Meteorological Towers',
                '1401': 'Abortional Act On Other',
                '5501': 'Drugs – Adulterated',
                '1402': 'Abortional Act On Self',
                '5502': 'Drugs – Misbranded',
                '1403': 'Submission To Abortional Act',
                '5503': 'Drugs – Other',
                '3002': 'Juvenile - Controlled Substance (Poss. Small Amount Of Marijuana)',
                '1404': 'Abortifacient',
                '5504': 'Drugs - Report Missing Precursor Substance',
                '5505': 'Drugs – Anhydrous Ammonia [pre 8/1/2005, replaced by codes in key d]',
                '1405': 'Distribute Articles & Information Regarding Unlawful Abortions',
                '5510': 'Food – Adulterated',
                '1406': 'Distribute Articles For Prevention Of Conception Or Disease',
                '5511': 'Food – Misbranded',
                '5512': 'Food – Other',
                '1407': 'Sale Of Articles For Prevention Of Conception Or Disease',
                '5520': 'Cosmetics – Adulterated',
                '5521': 'Cosmetics – Misbranded',
                '3003': 'Juvenile - Habitual Truant',
                '1408': 'Unlawful Advertisements For Cure Of Venereal/Sexual Disease',
                '5522': 'Cosmetics – Other',
                '3004': 'Juvenile – Petty Offender',
                '5531': 'Hazardous Waste - Knowing Endangerment',
                '3005': 'Juvenile - Use Of Tobacco',
                '1499': 'Abortion – Other',
                '5532': 'Hazardous Waste - Unlawful Disposal',
                '5313': 'Juvenile – Curfew',
                '5533': 'Hazardous Waste-Unlawful Treatment/False Statement',
                '5350': 'Juvenile – Runaway',
                '5534': 'Hazardous Waste-Negligent Violation',
                '5355': 'Juvenile - Incorrigible Juvenile',
                '5535': 'Hazardous Waste-Failure To Report Release',
                '5536': 'Hazardous Waste-Water Pollution',
                '5537': 'Hazardous Waste-Information And Monitoring',
                '5538': 'Hazardous Waste-Lead Acid Battery Disposal/Transportation',
                '5539': 'Hazardous Waste-Infectious Waste',
                '5540': 'Pipeline Safety-Failure To Report Emergency Release',
                '5551': 'Exposing Domestic Animals to Disease',
                '5555': 'Fail to Control Dangerous Animal Result in Bodily Harm',
                '5556': 'Fail to Control Dangerous Animal- Substantial Harm',
                '5557': 'Fail to Control Dangerous Animal-Death/Great Bodily Harm',
                '5558': 'Dangerous Dog Violations',
                '5560': 'Smoking Ban Violations',
                '5570': 'Tattoo/Body Pierce Without License',
                '5580': 'Adulteration by Bodily Fluid',
                '5599': 'Health/Safety – Other',
                '6701': 'Unlawfully Obtaining Services',
                '6201': 'Conservation - Animals',
                '6702': 'Unlawful Interference With Transit Operator-Misdemeanor',
                '6202': 'Conservation - Fish',
                '6703': 'Prohibited Acts',
                '6203': 'Conservation - Birds',
                '6501': 'Possession Of Drug Paraphernalia [replaced by codes in key d]',
                '6704': 'Boarding Moving Engines Or Cars',
                '6204': 'Conservation-License/Stamp',
                '6502': 'Manufacture/Delivery Of Drug Paraphernalia [replaced by codes in key d]',
                '6705': 'Fraud In Obtaining Special Transportation Service',
                '6205': 'Conservation - Environment',
                '6503': 'Delivery Of Drug Paraphernalia To A Minor [replaced by codes in key d]',
                '6706': 'Unlawful Interference With Transit Operator-Felony',
                '6206': 'Eurasian Milfoil',
                '6504': 'Advertise Drug Paraphernalia [replaced by codes in key d]',
                '6707': 'Violate Transit Restraining Order',
                '6207': 'Order To Cease Harassing Conduct Interference / Taking Wild Animals',
                '6208': 'Hunting Under the Influence',
                '6209': 'Prohibited Invasive Aquatic Species',
                '6299': 'Conservation - Other'
            },

            {
                'COL': 'Misc (Digit 2)',
                'INC': [1,2,3,4]
            },

            {
                'COL': 'Misc (Digit 3)',
                'INC': [1,2,3,4]
            },

            {
                'COL': 'Misc (Digit 4)',
                'INC': [1,2,3,4]
            }
        ],

        'N': [
            'Disturbing Peace / Privacy / Communications',  # Complete

            {
                'COL': 'Level',
                '1': 'Felony',
                '2': 'Gross Misdemeanor',
                '3': 'Misdemeanor',
                '0': 'Unknown'
            },

            {
                'COL': 'Act (Digit 1)',
                'INC': [2,3],
                '01': 'Riot',
                '02': 'Unlawful Assembly',
                '03': 'Disorderly Conduct',
                '04': 'Permitting Public Nuisance',
                '05': 'Vagrancy',
                '06': 'Concealing Identity',
                '07': 'Public Nuisance',
                '08': 'Interference with Privacy (Peeping Tom)',
                '09': 'Opening Sealed Letter, Telegram or Package',
                '10': 'False Information to News Media',
                '11': 'Unauthorized Communication (Emergency Communications; Kidnappings)',
                '12': 'Divulging Telephone or Telegraph Message; Non-Delivery Use with Stalking',
                '13': 'Emergency Telephone Calls – 911',
                '14': 'Interfering with Cable Communications',
                '15': 'Interfering with Religious Observance',
                '16': 'Criminal Defamation',
                '17': 'Wiretapping/Bugging',
                '18': 'Manufacture/Distribute/Possess/Advertise Wiretapping/Bugging Devices',
                '19': 'Harassing Communications (Telephone or Non-Written)',
                '21': 'False Fire Alarm',
                '23': 'Harass, Abuse, Threaten by Mail or Deliveries',
                '24': 'Disorderly House',
                '25': 'Unlawful Smoking',
                '26': 'Unauthorized Release Patient Information',
                '27': 'Obtaining Information Under Improper Means',
                '28': 'Harassment Following Assault or Terroristic Threats',
                '29': 'Molestation of Human Remains/Burials',
                '30': 'Molestation of Tombstones/Monuments/Indian Burial Grounds',
                '31': 'Stalking',
                '32': 'Tamper with Fire Alarm',
                '33': 'Physical Interference with Access to Health Care',
                '34': 'Interference with Use of Public Property',
                '35': 'Civil Disorder',
                '36': 'Cellular Counterfeiting',
                '37': 'Violation of an Order for Protection',
                '38': 'Violation of a Harassment Restraining Order',
                '39': 'Violation of a Domestic Abuse No Contact Order',
                '40': 'Interference with Emergency Communications',
                '41': 'Disruption of Funeral or Burial Service',
                '42': 'False Emergency Call',
                '43': 'Nonconsensual Dissemination of Private Sexual Images',
                '44': 'Surreptitious Observation Device (Minor Victim and Sexual Intent)',
                '99': 'Other',
                '00': 'Unknown'
            },

            {
                'COL': 'Act (Digit 2)',
                'INC': [2,3],
            },

            {
                'COL': 'Characteristics',
                '1': 'Motivated by Bias',
                '2': 'By False Impersonation',
                '3': 'Liquor [disorderly house only]',
                '4': 'Prostitution [disorderly house only]',
                '5': 'Drugs [disorderly house only]',
                '6': 'Gambling [disorderly house only]',
                '0': 'Unknown / Not Applicable',
                'A': 'Possess/Use Dangerous Weapon [stalking only]',
                'B': 'Influence/Tamper/Retaliate Juror/Judicial Proceeding/Officer [stalking only]',
                'C': 'Victim Under 18 [stalking only]',
                'D': 'Within 10 Years of Previous Related Conviction [stalking only]',
                'E': 'Pattern of Harassing Conduct [stalking only]',
                'H': 'Victim under 18 and Sexual or Aggressive Intent [stalking only]',
                'J': 'Within 10 years of 2 or More Previous Related Convictions [stalking only]',
                'F': 'Death Results',
                'G': 'Victim Under 18 [interference with privacy only]',
                'K': 'Subsequent Offense'
            }
        ],

        'O': [
            'Obscenity',  # Complete

            {
                'COL': 'Level',
                '1': 'Felony',
                '2': 'Gross Misdemeanor',
                '3': 'Misdemeanor',
                '0': 'Unknown'
            },

            {
                'COL': 'Act',
                '1': 'Manufacture',
                '2': 'Sale ',
                '3': 'Promote Obscene Material',
                '4': 'Distribute Obscene Material',
                '5': 'Operate/Own Business That Shows Obscene Works',
                '6': 'Indecent Exposure',
                '7': 'Communicate Obscenities (Written)',
                '8': 'Communicate Obscenities (Telephone or Non-Written)',
                '9': 'Other',
                '0': 'Unknown',
                'A': 'Use Minor Sexual Performance',
                'B': 'Dissemination Pornographic Work',
                'C': 'Possession Pornographic Work'
            },

            {
                'COL': 'Type Material / Aggravating Factor',
                '1': 'Books/Pamphlets/Magazines Depicting Minors',
                '2': 'Motion Picture/Plays Depicting Minors',
                '3': 'Other Materials Depicting Minors',
                '4': 'Books/Pamphlets/Magazines',
                '5': 'Motion Picture/Plays Depicting Adults',
                '6': 'Other Materials Depicting Adults',
                '7': 'Letter',
                '8': 'Telephone Calls',
                '9': 'Other',
                '0': 'Unknown',
                'A': 'Subsequent Offense [minor sexual performance or possession of child pornography only]',
                'B': 'By Predatory Offender [minor sexual performance or possession of child pornography only]',
                'C': 'Child under 13 yrs. of Age [minor sexual performance or possession of child pornography only]',
                'D': 'Child under 14 yrs. of Age [minor sexual performance or possession of child pornography only] [effective 9/15/2021]'
            },

            {
                'COL': 'Audience',
                '1': 'Minor',
                '2': 'Adult',
                '3': 'Other',
                '0': 'Unknown'
            }
        ],

        'P': [
            'Property Damage / Risk from Property Damage / Trespass',

            {
                'COL': 'Level',
                '1': 'Felony',
                '2': 'Gross Misdemeanor',
                '3': 'Misdemeanor',
                '4': 'Felony Motivated by Bias',
                '5': 'Gross Misdemeanor Motivated by Bias',
                '7': 'Gross Misdemeanor 2 or More Priors',
                '0': 'Unknown'
            },

            {
                'COL': 'Act',
                '1': 'Damage to Property',
                '2': 'Dangerous Trespass/Related Act',
                '3': 'Trespass/Other Acts',
                '5': 'Exposure of Unused Refrigerator',
                '6': 'Littering/Unlawful Deposit Garbage',
                '7': 'Obstruction of Railroad Tracks',
                '8': 'Shoot/Throw Objects at Train',
                '9': 'Other',
                '0': 'Unknown',
                'A': 'Damages/Destroys Computer Hardware, Network or Software',
                'B': 'Alters Computer Hardware, Network or Software',
                'C': 'Distributes A Destructive Computer Program',
                'D': 'Dangerous Smoking',
                'E': 'Intentional Release Harmful Substance',
                'F': 'Interferes with Logging/Wood Processing Equipment',
                'G': 'Possession Timber Damage Devices',
                'H': 'Computer Access',
                'J': 'Facilitating Access to Computer Security System',
                'K': 'Damage or Theft to Energy Transmission / Telecommunications'
            },

            {
                'COL': 'Property',
                '1': 'Private',
                '2': 'Public',
                '3': 'Commercial/Business',
                '4': 'Utility/Common Carrier [pre 8/1/2007]',
                '5': 'Railroad',
                '6': 'Camp Ripley',
                '7': 'Agricultural Lands',
                '8': 'Computer/Programs',
                '9': 'Other',
                '0': 'Unknown',
                'A': 'Cemetery Monument',
                'B': 'Emergency Shelter for Battered Women',
                'C': 'Trade Secret',
                'D': 'Non-Public Data',
                'E': 'School Grounds',
                'F': 'Aircraft',
                'G': 'Common Carrier',
                'H': 'Utility',
                'J': 'Critical Public Service Facility Post',
                'K': 'Pipeline',
                'L': 'Public Safety Motor Vehicle',
                'M': 'School Bus',
                'N': 'Electronic Terminal',
            },

            {
                'COL': 'Intent / Risk / Damage',
                '1': 'Intent to Injure',
                '2': 'Risk Injury/Death-Endanger Safety',
                '3': 'Impairs Service (Utility/Common Carrier)',
                '4': 'Reduces Value by More Than $500',
                '5': 'Risk of Serious Property Damage',
                '6': 'Hunting',
                '9': 'Other',
                '0': 'Unknown / Not Applicable',
                'A': 'Reduces Value By $251-$499 [pre 8/1/2007]',
                'B': 'Reduces Value by More Than $250 And Previous Conviction',
                'C': 'Reduces Value By $250 Or Less',
                'D': 'Computer Damage-Over $2500',
                'E': 'Computer Damage-$501-$2500',
                'F': 'Computer Damage-$500 Or Less',
                'G': 'Significantly Disrupt Operation or Services',
                'H': 'Reduces Value by More Than $1,000-Fel.',
                'J': 'Reduces Value by More Than $500 and Previous Conviction-Felony',
                'K': 'Reduces Value by $501-$1, 000 - G. Misd.',
                'L': 'Reduces Value by $500 or Less - Misd.'

            }
        ],

        'Q': [
            'Stolen Property (Receiving / Concealing)',

            {
                'COL': 'Level',
                '1': 'Felony',
                '2': 'Gross Misdemeanor',
                '3': 'Misdemeanor',
                '0': 'Unknown'
            },

            {
                'COL': 'Act',
                '1': 'Receive',
                '2': 'Possesses',
                '3': 'Transfer',
                '4': 'Buys',
                '5': 'Conceal',
                '6': 'Bring Stolen Property Into State',
                '9': 'Other',
                '0': 'Unknown'
            },

            {
                'COL': 'Type of Property',
                '1': 'Precious Metals',
                '2': 'Vehicles',
                '3': 'Guns',
                '4': 'Scrap Metal',
                '9': 'Other',
                '0': 'Unknown'
            },

            {
                'COL': 'Property Value',
                '1': 'Greater Than $2,500 [pre 8/1/2007]',
                '2': '$1,000 - $2,500 [pre 8/1/2007]',
                '3': '$301 - $999 [pre 8/1/2007]',
                '4': '$300 or Less [pre 8/1/2007]',
                '5': 'Greater Than $35,000 [pre 8/1/2007]',
                '6': '$2,501 - 34,999 [pre 8/1/2007]',
                '7': '$501 - $2,500 [pre 8/1/2007]',
                '8': '$201 - $500 [pre 8/1/1999]',
                '9': '$200 or Less [pre 8/1/1999]',
                '0': 'Unknown',
                'A': '$251-$500 [pre 8/1/2007]',
                'B': '$250 or Less [pre 8/1/2007]',
                'C': 'More Than $5,000-Felony [post 8/1/2007]',
                'D': '$1,001-$5,000-Felony [post 8/1/2007]',
                'E': '$501-$1,000 and Previous Conviction-Felony [post 8/1/2007]',
                'F': '$501-$1,000-Gross Misdemeanor [post 8/1/2007]',
                'G': '$500 or Less-Misdemeanor [post 8/1/2007]',
                'H': 'Greater than $1,000 [precious metals and scrap metal only] [post 8/1/2007]',
                'J': '$501-$1,000 [precious metals and scrap metal only] [post 8/1/2007]',
                'K': 'Subsequent Offenses [precious metals and scrap metal only] [post 8/1/2007]',
                'L': '$500 Or Less-Misdemeanor [precious metals and scrap metal only] [post 8/1/2007]',
            }
        ],

        'R': [
            'Robbery',

            {
                'COL': 'Category',
                '1': 'Aggravated (Inflicted Bodily Harm)',
                '2': 'Aggravated (None or Less Than Bodily Harm)',
                '3': 'Simple',
                '0': 'Unknown'
            },

            {
                'COL': 'Type',
                '1': 'Highway (Street, Alley, Etc.)',
                '2': 'Commercial House (Except 3, 4, or 6)',
                '3': 'Gas or Service Station',
                '4': 'Convenience Store',
                '5': 'Residence',
                '6': 'Bank',
                '7': 'Forcible Purse Snatch',
                '8': 'Carjacking',
                '9': 'Other',
                '0': 'Unknown'
            },

            {
                'COL': 'Weapon Used',
                '1': 'Firearm (Possess Only)',
                '2': 'Firearm',
                '3': 'Knife / Cutting Instrument',
                '4': 'Other Dangerous Weapon',
                '5': 'Strong Arm (Hands, Fists, Feet, Etc.)',
                '6': 'Explosives',
                '7': 'Replica Firearm',
                '8': 'Feigned Weapon',
                '9': 'None',
                '0': 'Unknown'
            },

            {
                'COL': 'Victim',
                '1': 'Adult - Family',
                '2': 'Adult - Acquaintance',
                '3': 'Adult - Stranger',
                '4': 'Child - Family',
                '5': 'Child - Acquaintance',
                '6': 'Child - Stranger',
                '0': 'Unknown'
            }
        ],

        'S': [
            'Criminal Sex (Historical)',

            {
                'COL': 'Not Documented'
            },

            {
                'COL': 'Not Documented'
            },

            {
                'COL': 'Not Documented'
            },

            {
                'COL': 'Not Documented'
            }
        ],

        'T': [  # Complete, untested
            'Theft',

            {
                'COL': 'Level / Value',
                '0': 'Unknown',
                'A': 'More Than $35,000 – Felony',
                'B': 'More Than $2,500 - Felony [pre 8/1/2007]',
                'C': '$501-$2,500 – Felony [pre 8/1/2007]',
                'D': 'Not More Than $500 - Felony [pre 8/1/2007]',
                'E': 'Other – Felony',
                'F': '$201-$500 - Gross Misdemeanor [pre 8/1/99]',
                'G': '$200 or Less - Misdemeanor [pre 8/1/99]',
                'Q': '$251-500 - Gross Misdemeanor [pre 8/1/2007]',
                'R': '$250 or Less - Misdemeanor [pre 8/1/2007]',
                'H': 'More Than $2,500 - Gross. Misd.',
                'J': 'More Than $2,500 - Misdemeanor',
                'K': '$501-$2,500 - Gross. Misd.',
                'M': '$501-$2,500 - Misdemeanor',
                'N': '$201-500 - Misdemeanor',
                'P': 'Juv. Petty Misdemeanor',
                'S': 'More Than $5,000-Felony',
                'T': '$1,001-$5,000-Felony',
                'U': '$501-$1,000 and Prev. Convict.-Felony',
                'V': '$501-$1,000-Gross Misd.',
                'W': '$500 or Less-Misdemeanor',
                'X': 'Reasonably Foreseeable Risk of Bodily Harm – Felony',
                'Y': 'Not More Than $1,000 – Felony',
                'Z': 'Embezzlement'
            },

            {
                'COL': 'From (Digit 1)',
                'INC': [2,3],
                '01': 'Person',
                '02': 'Building',
                '03': 'Coin Machine',
                '04': 'Shipment',
                '05': 'Yards',
                '06': 'Mail',
                '07': 'Bank-Type Institution',
                '08': 'Interstate Shipment',
                '09': 'Self-Service Gas Station (Gas Only)',
                '10': 'Public Funds',
                '11': 'Business Funds',
                '12': 'U.S. Government Reservation',
                '13': 'Burning/Vacant/Abandoned Building or Disaster Area (Looting)',
                '14': 'Cable Communications Systems',
                '15': 'Motor Vehicle',
                '16': 'Watercraft',
                '17': 'Postal',
                '18': 'Fish houses',
                '19': 'Military',
                '20': 'Full Service Gas Station (Gas Only)',
                '22': 'Street/Parking Lot/Driveway',
                '23': 'Telecommunication System',
                '24': 'Wrongful Employment -Child Care Center',
                '25': 'Wage(s)',
                '99': 'Other',
                '00': 'Unknown/NA'
            },

            {
                'COL': 'From (Digit 2)',
                'INC': [2,3]
            },

            {
                'COL': 'Of',
                '1': 'Money/Other Negotiables',
                '2': 'Services',
                '3': 'Court Or Public Records',
                '4': 'Trade Secrets',
                '5': 'Firearms',
                '6': 'Livestock',
                '7': 'Herbicides, Pesticides, Etc.',
                '8': 'Grain',
                '9': 'Other Property',
                '0': 'Unknown/NA',
                'A': 'Explosives',
                'B': 'Incendiary Device',
                'C': 'Schedule I or II Cont. Subs.',
                'D': 'Schedule III IV or V Cont. Subs.'
            }
        ],

        'U': [
            'Theft Related',

            {
                'COL': 'Level / Value'
            },

            {
                'COL': 'Act (Digit 1)'
            },

            {
                'COL': 'Act (Digit 2)'
            },

            {
                'COL': 'Property Loss / Value'
            }
        ],

        'V': [
            'Vehicle Theft Related',

            {
                'COL': 'Level / Value'
            },

            {
                'COL': 'Act (Digit 1)'
            },

            {
                'COL': 'Act (Digit 2)'
            },

            {
                'COL': 'Vehicle Type'
            }
        ],

        'W': [  # Complete
            'Weapons',

            {
                'COL': 'Level',
                '1': 'Felony',
                '2': 'Gross Misdemeanor',
                '3': 'Misdemeanor',
                '4': 'Gross Misdemeanor - 2 or More Priors',
                '0': 'Unknown'
            },

            {
                'COL': 'Act',
                '1': 'Operate/Discharge/Set',
                '2': 'Recklessly Handles',
                '3': 'Points',
                '4': 'Manufacture/Sell',
                '5': 'Carry/Transport',
                '6': 'Possess/Own',
                '7': 'Furnish',
                '8': 'Alter/Remove Serial Numbers',
                '9': 'Other',
                '0': 'Unknown',
                'A': 'Use Against Peace Officer In Performance Of Duties',
                'B': 'Use/Possess During Crime',
                'C': 'Causes Death/Great Bodily Harm',
                'D': 'Causes Substantial Bodily Harm',
                'E': 'Reckless Discharge within Municipality',
                'F': 'Negligently Stores-Child Likely to Gain Access',
                'G': 'Carries in Public Place',
                'H': 'Drive By Shooting',
                'J': 'Transfer w/out Background Check',
                'K': 'Transfer to Ineligible Person',
                'L': 'Possess in Courthouse/Capitol',
                'M': 'Witness Firearm Discharge',
                'N': 'Other Transfer Violations',
                'O': 'Make Readily Accessible to Another',
                'P': 'Displays',
                'Q': 'Threatens to Use',
                'R': 'Communicates WOMD',
                'S': 'Predatory Offender Carrying Pistol',
                'T': 'Allow Access to Abusing Party',
                'U': 'Purchase on Behalf of Ineligible Person'
            },

            {
                'COL': 'Type',
                '1': 'Machine Gun/Short Barrel Shotgun',
                '2': 'Pistol',
                '3': 'Saturday Night Special',
                '4': 'Firearm',
                '5': 'Explosive/Incendiary',
                '6': 'Silencer/Suppressor',
                '7': 'Spring Gun/Pitfall/Snare',
                '8': 'Fireworks',
                '9': 'Other',
                '0': 'Unknown',
                'A': 'Electronic Incapacitation Device',
                'B': 'Metal Penetrating Bullets',
                'C': 'Bullet Resistant Vest',
                'D': 'Tear Gas',
                'E': 'Semiautomatic Military Style Assault Weapon',
                'F': 'Machine Gun Conversion Kit',
                'G': 'Trigger Activator',
                'H': 'Replica Firearm',
                'J': 'B.B. Gun',
                'K': 'Weapon of Mass Destruction',
                'L': 'Simulated Weapon of Mass Dest.',
                'M': 'Prohibited Substances',
                'N': 'Ammunition'
            },

            {
                'COL': 'Offense Characteristics',
                '1': 'Furnishes A Child - Under 14 Yrs. Old',
                '2': 'Furnishes A Minor - Under 18 Yrs. Old',
                '3': 'Person Convicted Of Violent Crime',
                '4': 'Mentally Ill',
                '5': 'Person Convicted Cont. Sub. Crime',
                '6': 'Inebriate',
                '7': 'Licensing Violation',
                '8': 'Registration Violation',
                '9': 'Other',
                '0': 'Unknown',
                'A': 'Circumstances Endanger Safety Of Another',
                'B': 'Fails To Render Assistance.',
                'C': 'In Park Public Housing or School Zone',
                'D': 'Reckless Furnishing',
                'E': 'Person under 18 Possesses',
                'F': 'Prior Assault Family / Household Member',
                'G': 'Charged / Convicted Viol Crime - Diverted',
                'H': 'On School Property',
                'I': 'Terrorize/Cause Evacuation-Disruption',
                'J': 'Person [drive by shooting only]',
                'K': 'Motor Vehicle [drive by shooting only]',
                'L': 'Motor Vehicle-Occupied [drive by shooting only]',
                'M': 'Building [drive by shooting only]',
                'N': 'Building – Occupied [drive by shooting only]',
                'O': 'Transit Vehicle/Facility',
                'P': 'Transit Vehicle/Facility - Occupied',
                'Q': 'Convicted of Stalking',
                'R': 'Convicted Crime Punishable by Imprisonment For More Than 1 Year',
                'S': 'Charged Crime Punishable by Imprisonment For More Than 1 Year',
                'T': 'Fugitive From Justice',
                'U': 'Dishonorable Discharge',
                'V': 'Illegal Alien',
                'W': 'Person Has Renounced Citizenship',
                'X': 'While Under Influence Alcohol/ Con. Sub.',
                'Y': 'Uses in Violent Felony w/in one Year',
                'Z': 'Convicted of Violating an Order for Protection'
            }
        ],

        'X': [
            'Crime Against Administration of Justice',  # Complete

            {
                'COL': 'Level',
                '1': 'Felony',
                '2': 'Gross Misdemeanor',
                '3': 'Misdemeanor',
                '0': 'Unknown'
            },

            {
                'COL': 'Act (Digit 1)',
                'INC': [2,3],
                '01': 'Perjury Upon Felony Trial',
                '02': 'Perjury on Explosive License Application',
                '03': 'Perjury – Other',
                '04': 'Tampering with Witness',
                '05': 'Misconduct of Judicial or Hearing Officer',
                '06': 'Simulating Legal Process',
                '07': 'Interference with Dead Body or Scene of Death',
                '08': 'Obstructing Legal Process or Arrest (Peace Officer / Department of Revenue Employee)',
                '09': 'Bringing Contraband into Jail / Correctional Facility',
                '10': 'Bringing Dangerous Weapon into Jail / Correctional Facility',
                '11': 'Refusing to Make Arrest or To Aid Officer',
                '12': 'Contempt of Court',
                '13': 'Probation Violation',
                '14': 'Parole Violation',
                '15': 'Conspiracy to Cause False Arrest or Prosecution (Only Crime Charged)',
                '16': 'Conspire to Commit A Crime (Only Crime Charged)',
                '17': 'Conspiracy Prohibited (Drug Related)',
                '19': 'Falsely Reporting Crime',
                '20': 'Give False Name to Police (M.S.§609.506)',
                '21': 'Falsely Reporting Child Abuse',
                '23': 'Kill or Harm a Public Safety Dog',
                '24': 'Obstruct Firefighting',
                '25': 'Violation of Order for Protection [pre 8/1/97]',
                '26': 'Use of Police Radio During Commission of a Felony',
                '27': 'Use of Police Radio While Fleeing Police Officer in Motor Vehicle',
                '28': 'Concealing Criminal Proceeds',
                '29': 'Engaging in Business of Concealing Criminal Proceeds',
                '30': 'Racketeering',
                '31': 'Warning Subject of Investigation',
                '32': 'Warning Subject of Surveillance or Search',
                '33': 'Failure to Report Removal of Dead Body from Cemetery',
                '34': 'Failure to Appear for Jury Service',
                '35': 'Solicit Juvenile to Commit Criminal Act',
                '36': 'Violation Harassment Restraining Order [pre 8/1/97]',
                '37': 'Illegal Armed Association',
                '38': 'Obstructing Public Levees',
                '39': 'Solicit Mentally Impaired Person to Commit Criminal Act',
                '40': 'Sex Offenders Required to Register',
                '41': 'Assaulting or Harming a Police Horse',
                '42': 'Possession of Police Radio',
                '43': 'Aggravated First Degree Witness Tampering',
                '44': 'Reside in MN Without Permission Under Interstate Compact',
                '45': 'Refuse to Cooperate with Insurance Fraud Investigation',
                '46': 'Disarm Police',
                '47': 'Unmanned Aerial Vehicle (UAV) Over State Correction Facility',
                '99': 'Other',
                '00': 'Unknown'
            },

            {
                'COL': 'Act (Digit 2)',
                'INC': [2,3],
            },

            {
                'COL': 'Filler',
                '0': 'All Circumstances'
            }
        ],

        'Y': [
            'Crime Against Government - Public Official',  # Complete

            {
                'COL': 'Level',
                '1': 'Felony',
                '2': 'Gross Misdemeanor',
                '3': 'Misdemeanor',
                '0': 'Unknown'
            },

            {
                'COL': 'Act (Digit 1)',
                'INC': [2,3],
                '01': 'Treason',
                '02': 'Treason Misprision',
                '03': 'Interfering of State Military Force',
                '04': 'Flags Code',
                '06': 'False Tax Statement',
                '07': 'Bribery',
                '08': 'Corruptly Influencing Legislator',
                '09': 'Misconduct of Public Officer or Employer',
                '10': 'Officer Not Filing Security',
                '11': 'Public Office - Illegally Assuming / Nonsurrender',
                '12': 'Failure to Pay Over State Funds',
                '13': 'Public Officer - Unauthorized Compensation',
                '14': 'Permitting False Claims Against Government',
                '15': 'Interference with Property in Official Custody',
                '16': 'Impersonating Officer',
                '17': 'Altering Engrossed Bill',
                '18': 'Desertion',
                '19': 'Election Laws',
                '20': 'Contempt of Legislature',
                '21': 'Disturbing Legislature or Intimidating Member',
                '22': 'Unauthorized Disposal or Destruction of Records',
                '23': 'Intent to Escape Tax - Motor Vehicle',
                '24': 'Watercraft Certificate of Title - Prohibited Acts',
                '25': 'Government Purchasing - False Information',
                '26': 'Unclaimed / Abandoned Property',
                '50': 'Income Tax Offense',
                '51': 'Sales Tax Offense',
                '52': 'Liquor Tax Offense',
                '53': 'Other Tax Offenses',
                '54': 'Failure to File - Marijuana / Controlled Substance',
                '55': 'Filing False / Fraudulent Return - Marijuana / Controlled Substance',
                '56': 'Intent to Evade Tax - Marijuana / Controlled Substance',
                '57': 'Stamps Affixed - Marijuana / Controlled Substance',
                '58': 'Gambling Tax Offense',
                '59': 'Insurance Tax Offense',
                '60': 'Motor Vehicle Excise Tax Offense',
                '61': 'Fraudulent or Improper Financing Statements',
                '62': 'Reports by Dealers in Scrap Metal',
                '63': 'Impersonating Officer – Peace Officer Authorized',
                '64': 'Violation of a licensing order',
                '65': 'Impersonating Military Service Member, Veteran, Public Official',
                '66': 'Automated Sales Suppression Device, Zapper, Phantom-ware',
                '67': 'Geographic Restriction Order',
                '68': 'Teacher’s License Fraud',
                '69': 'Misuse of Doctor’s Title',
                '99': 'Other',
                '00': 'Unknown'
            },

            {
                'COL': 'Act (Digit 2)',
                'INC': [2,3]
            },

            {
                'COL': 'Filler',
                '0': 'All Circumstances'
            }
        ],

        'Z': [
            'Sex Related',

            {
                'COL': 'Level',
                '1': 'Felony',
                '2': 'Gross Misdemeanor',
                '3': 'Misdemeanor',
                '4': 'Gross Misdemeanor - 2 or More Priors',
                '5': 'Gross Misdemeanor Offense Committed in School or Park Zone (Felony)',
                '6': 'Misdemeanor Offense Committed in School or Park Zone (Gross Misdemeanor)',
                '0': 'Unknown'
            },

            {
                'COL': 'Act',
                '1': 'Solicitation',
                '2': 'Inducement',
                '3': 'Promotion',
                '4': 'Consents to Individual Being Taken or Detained',
                '5': 'Receive Profit Applies to Prostitution Offenses',
                '6': 'Engages / Hires / Offers or Agrees to Hire',
                '7': 'Sodomy',
                '8': 'Bestiality',
                '9': 'Other Prohibited Acts',
                '0': 'Unknown / Not Applicable',
                'A': 'Solicit Child to Engage in Sexual Conduct',
                'B': 'Loitering with Intent to Participate in Prostitution',
                'C': 'Electronic Solicitation of Children',
                'D': 'Sex Trafficking - Individual Under 18 yrs [pre 8/1/98]',
                'E': 'Patron of Prostitution [new 2021]'
            },

            {
                'COL': 'Offense Characteristics',
                '1': 'Offender is Prostitute',
                '8': 'Prostitution',
                'A': 'School Zone [prostitution offenses only]',
                'B': 'Park Zone',
                'C': 'Public Place(actor is prostitute)',
                'D': 'Public Place(actor is patron)',
                '0': 'Unknown / Not Applicable',
                '2': 'Prostitute Induced by Force',
                '3': 'Prostitute Induced by Position of Authority',
                '4': 'Prostitute Induced by Means of Trick, Fraud, or Deceit',
                '5': 'Position of Authority - Consent to Individual Being Taken or Detained'
            },

            {
                'COL': 'Age of Prostitute',
                '1': 'Less Than 16 Years of Age',
                '2': '16 - 17 Years Old',
                '3': '18 Years Old or Older',
                '4': 'Less Than 13 Years of Age',
                '5': '13 - 15 Years Old',
                '6': 'Not Prostitute',
                '7': 'Believes to be a Child',
                '0': 'Unknown'
            }
        ]
    }
