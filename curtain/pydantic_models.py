from typing import List, Optional
from pydantic import BaseModel, HttpUrl, Field

class Affiliation(BaseModel):
    affiliation: str
    affiliationIdentifier: Optional[str] = None
    affiliationIdentifierScheme: Optional[str] = None
    affiliationSchemeURI: Optional[HttpUrl] = None

class Creator(BaseModel):
    givenNames: Optional[str] = None
    familyName: Optional[str] = None
    name: str
    nameType: str
    nameIdentifier: str
    nameIdentifierScheme: str
    schemeURI: HttpUrl
    affiliations: List[Affiliation]

class Title(BaseModel):
    title: str
    language: str

class ResourceType(BaseModel):
    resourceTypeGeneral: str
    resourceType: str

class Subject(BaseModel):
    subject: str
    subjectScheme: str
    valueURI: HttpUrl

class Contributor(BaseModel):
    name: str
    affiliations: List[Affiliation]
    givenNames: Optional[str] = None
    familyName: Optional[str] = None
    nameIdentifier: Optional[str] = None
    nameIdentifierScheme: Optional[str] = None
    nameType: str
    schemeURI: HttpUrl

class Description(BaseModel):
    description: str
    descriptionType: str

class Rights(BaseModel):
    rights: str
    rightsUri: HttpUrl

class AlternateIdentifier(BaseModel):
    alternateIdentifier: str
    alternateIdentifierType: str

class RelatedIdentifier(BaseModel):
    relatedIdentifier: Optional[str] = None
    relatedIdentifierType: Optional[str] = None
    relationType: Optional[str] = None
    relatedMetadataScheme: Optional[str] = None
    schemeURI: Optional[HttpUrl] = None
    schemeType: Optional[str] = None
    resourceTypeGeneral: Optional[str] = None

class FundingReference(BaseModel):
    funderName: Optional[str] = None
    funderIdentifier: Optional[str] = None
    funderIdentifierType: Optional[str] = None
    schemeURI: Optional[HttpUrl] = None
    awardNumber: Optional[str] = None
    awardURI: Optional[HttpUrl] = None
    awardTitle: Optional[str] = None

class DataCiteForm(BaseModel):
    prefix: str
    suffix: str
    url: HttpUrl
    creators: List[Creator]
    titles: List[Title]
    publisher: str
    publisherIdentifier: HttpUrl
    publicationYear: int
    resourceType: ResourceType
    subjects: List[Subject]
    contributors: List[Contributor]
    descriptions: List[Description]
    rightsList: List[Rights]
    alternateIdentifiers: List[AlternateIdentifier]
    relatedIdentifiers: List[RelatedIdentifier]
    fundingReferences: List[FundingReference]