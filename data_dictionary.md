# NYC Campaign Finance Board Data Dictionary

## Overview
This document describes the fields in the NYC Campaign Finance Board (CFB) political contribution dataset. The data covers campaign finance records for NYC municipal elections including contributions, expenditures, and public matching funds.

## Field Definitions

### Election & Campaign Fields

| Field | Type | Description | Values |
|-------|------|-------------|---------|
| **ELECTION** | String | Election cycle identifier | Examples: '2001', '2021', '2025'<br>Suffix meanings:<br>- 'T' = Transition<br>- 'A' = Special election<br>- 'U' = Unknown type |
| **OFFICECD** | String | Office code for the position | 1 = Mayor<br>2 = Public Advocate<br>3 = Comptroller<br>4 = Borough President<br>5 = City Council Member<br>6 = Unknown/Other<br>11, 44, 55 = Special designations<br>IS = Independent spending |
| **RECIPID** | String | Unique identifier for recipient/candidate | Numeric ID assigned by CFB |
| **CANCLASS** | String | Candidate classification | P = Participating (receives public matching funds)<br>NP = Non-participating<br>UN = Unknown/Unclassified |
| **RECIPNAME** | String | Name of recipient (candidate/committee) | Full name in "Last, First" format |
| **COMMITTEE** | String | Committee type indicator | H = Principal committee<br>Other values indicate committee types |

### Filing & Disclosure Fields

| Field | Type | Description | Values |
|-------|------|-------------|---------|
| **FILING** | Integer | Filing period number | Sequential number indicating which disclosure period |
| **SCHEDULE** | String | Disclosure schedule type | ABC = Contributions<br>D = Expenditures<br>M = Matchable contributions<br>ICONT = In-kind contributions |
| **PAGENO** | Float | Page number in filing | Page reference in original paper filing |
| **SEQUENCENO** | Float | Sequence number | Order within filing |
| **REFNO** | String | Reference number | Unique transaction reference |

### Contribution Details

| Field | Type | Description | Values |
|-------|------|-------------|---------|
| **DATE** | String | Transaction date | MM/DD/YYYY format |
| **REFUNDDATE** | String | Refund date (if applicable) | MM/DD/YYYY format |
| **AMNT** | Float | Contribution amount | Dollar amount |
| **MATCHAMNT** | Float | Public matching funds amount | Dollar amount matched by NYC |
| **PREVAMNT** | Float | Previous amount | For amended filings |
| **PAY_METHOD** | Integer | Payment method code | 1 = Cash<br>2 = Check<br>3 = Credit card<br>4 = Electronic transfer<br>5 = Other |

### Contributor Information

| Field | Type | Description | Values |
|-------|------|-------------|---------|
| **NAME** | String | Contributor name | Individual or organization name |
| **C_CODE** | String | Contributor type code | IND = Individual<br>CORP = Corporation<br>LLC = Limited Liability Company<br>PART = Partnership<br>EMPO = Employee organization<br>PCOMP = Political committee<br>PCOMC = Political committee (other)<br>OTHR = Other<br>UNKN = Unknown |
| **OCCUPATION** | String | Contributor's occupation | Free text field |
| **EMPNAME** | String | Employer name | Contributor's employer |

### Address Information

| Field | Type | Description | Values |
|-------|------|-------------|---------|
| **STRNO** | Float | Street number | Numeric portion of address |
| **STRNAME** | Float | Street name | Street portion of address |
| **APARTMENT** | Float | Apartment/unit number | Secondary address info |
| **BOROUGHCD** | String | Borough code | M = Manhattan<br>K = Brooklyn<br>Q = Queens<br>X = Bronx<br>S = Staten Island<br>Z = Outside NYC |
| **CITY** | String | City name | Municipality |
| **STATE** | String | State abbreviation | Two-letter state code |
| **ZIP** | String/Float | ZIP code | 5-digit postal code |

### Employer Address Fields

| Field | Type | Description |
|-------|------|-------------|
| **EMPSTRNO** | String | Employer street number |
| **EMPSTRNAME** | String | Employer street name |
| **EMPCITY** | String | Employer city |
| **EMPSTATE** | String | Employer state |

### Intermediary Fields (for bundled contributions)

| Field | Type | Description |
|-------|------|-------------|
| **INTERMNO** | Float | Intermediary number |
| **INTERMNAME** | String | Intermediary name |
| **INTSTRNO** | Float | Intermediary street number |
| **INTSTRNM** | Float | Intermediary street name |
| **INTAPTNO** | Float | Intermediary apartment |
| **INTCITY** | String | Intermediary city |
| **INTST** | String | Intermediary state |
| **INTZIP** | String | Intermediary ZIP |
| **INT_C_CODE** | String | Intermediary contributor code |

### Intermediary Employer Fields

| Field | Type | Description |
|-------|------|-------------|
| **INTEMPNAME** | String | Intermediary employer name |
| **INTEMPSTNO** | String | Intermediary employer street number |
| **INTEMPSTNM** | String | Intermediary employer street name |
| **INTEMPCITY** | String | Intermediary employer city |
| **INTEMPST** | String | Intermediary employer state |
| **INTOCCUPA** | String | Intermediary occupation |

### Other Fields

| Field | Type | Description | Values |
|-------|------|-------------|---------|
| **PURPOSECD** | String | Purpose code (for expenditures) | RENTO = Rent<br>CATER = Catering<br>Various expense codes |
| **EXEMPTCD** | String | Exemption code | Indicates exempt contributions |
| **ADJTYPECD** | Float | Adjustment type code | 1 = Addition<br>2 = Deletion<br>3 = Modification |
| **RR_IND** | String | Registered recipient indicator | Y = Yes<br>N = No |
| **SEG_IND** | String | Segregated account indicator | Y = Yes<br>N = No |

## Data Quality Notes

1. **NULL Values**: Many fields contain NULL values, particularly address fields and intermediary information
2. **Date Format**: Dates are stored as strings in MM/DD/YYYY format
3. **Name Format**: Recipient names typically use "Last, First" format; contributor names vary
4. **Amount Fields**: All monetary amounts are in US dollars
5. **Mixed Types**: Some columns (STRNO, STRNAME) are stored as float type but contain address data

## Common Use Cases

1. **Contribution Analysis**: Use NAME, AMNT, DATE to analyze contribution patterns
2. **Geographic Analysis**: Use BOROUGHCD, CITY, STATE for location-based analysis
3. **Candidate Performance**: Use RECIPID, RECIPNAME, ELECTION to track candidate fundraising
4. **Matching Funds**: Use MATCHAMNT to analyze public financing impact
5. **Contributor Networks**: Use intermediary fields to identify bundled contributions

## Important Considerations

- **Privacy**: This data contains personal information and should be handled responsibly
- **Accuracy**: Data is self-reported by campaigns and may contain errors
- **Updates**: The CFB regularly updates data; check for the latest version
- **Legal Compliance**: Ensure any use complies with campaign finance laws and regulations