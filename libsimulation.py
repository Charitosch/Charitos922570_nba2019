import json
import re
import urllib.parse
from typing import Callable
import requests
import pandas
import time

class SimulationSettings:
    env: str
    cutoff: str
    resultpath: str
    predict: Callable

def _getRequest(url):
    r = requests.get(url)
    if r.status_code < 200 or r.status_code > 299:
        raise Exception(f'Could not obtain data from url {url}. Server responded with status code {r.status_code}')
    return r.json()

class NbaDataLoader:
    def __init__(self, settings: SimulationSettings):
        self.settings = settings
        self.playerColumns = [
            'gameId',
            'name',
            'dateTime',
            'team',
            'season',
            'blocks',
            'injuryBodyPart',
            'injuryStatus',
            'minutes',
            'points',
            'position',
            'rebounds',
            'steals'
        ]

    # Obtain the games of a season.
    # Seasons are strings such as '2009' or '2010POST'
    # The earliest available season is '2009'
    def getSeason(self, season: str):
        data = _getRequest(f'https://{self.settings.env}api.nbadatachallenge.com/data/seasons/{urllib.parse.quote(season)}')
        result = []
        for d in data:
            dateTime = d['dateTime']
            if (dateTime is not None) and dateTime < self.settings.cutoff:
                result.append(d)
        return pandas.DataFrame(result, columns=['gameId', 'dateTime', 'homeTeam', 'awayTeam', 'homeBlocks', 'homeMinutes', 'homeRebounds', 'homeScore', 'homeSteals', 'quarter0home', 'quarter1home', 'quarter2home', 'quarter3home', 'awayBlocks', 'awayMinutes', 'awayRebounds', 'awayScore', 'awaySteals', 'quarter0away', 'quarter1away', 'quarter2away', 'quarter3away', 'season', 'status'])

    # Obtain a single game data
    # The gameId is a numerical game identifier.
    # You can find the gameId from the results of getSeason
    def getGame(self, gameId: int):
        data = _getRequest(f'https://{self.settings.env}api.nbadatachallenge.com/data/games/{urllib.parse.quote(str(gameId))}')
        result = []
        for d in data:
            dateTime = d['dateTime']
            if dateTime < self.settings.cutoff:
                result.append(d)
        return pandas.DataFrame(result, columns=self.playerColumns)

    # Obtain full player data about all the games in a season.
    def getPlayers(self, season: str):
        data = _getRequest(f'https://{self.settings.env}api.nbadatachallenge.com/data/gameplayersfull/{urllib.parse.quote(season)}')
        result = []
        for d in data:
            dateTime = d['dateTime']
            if dateTime < self.settings.cutoff:
                result.append(d)
        return pandas.DataFrame(result, columns=self.playerColumns)

def _loadPredictions(settings: SimulationSettings):
    return _getRequest(f'https://{settings.env}api.nbadatachallenge.com/data/predictions/{urllib.parse.quote(settings.cutoff)}')

def _sanitizeResult(results, predictions):
    if len(results) != len(predictions):
        raise Exception(f'User returned {len(results)} predictions, but expecting {len(predictions)} predictions')
    sanitized = []
    for result in results:
        if not isinstance(result['gameId'], int):
            raise Exception(f'gameId field in the prediction must be an int')
        if not isinstance(result['sum'], float):
            raise Exception(f'sum field in the prediction must be a float')
        if not isinstance(result['diff'], float):
            raise Exception(f'diff field in the prediction must be a float')
        sanitized.append({
            'gameId': result['gameId'],
            'sum': result['sum'],
            'diff': result['diff']
        })
    return sanitized

def _findByGameId(results, gameId):
    for r in results:
        if r['gameId'] == gameId:
            return r
    return None

def _getField(doc, field):
    if doc is None:
        return 'None'
    if field in doc:
        return doc[field]
    else:
        return 'None'

def _computeSum(a, b):
    if a is None or b is None:
        return None
    return a + b

def _computeDiff(a, b):
    if a is None or b is None:
        return None
    return a - b

def _displayPredictionsAndResults(results, actual):
    for game in actual:
        gameId = game['gameId']
        resultGame = _findByGameId(results, gameId)
        homeScore = _getField(game, 'homeScore')
        awayScore = _getField(game, 'awayScore')
        actualSum = _computeSum(homeScore, awayScore)
        actualDiff = _computeDiff(homeScore, awayScore)
        sumPredicted = _getField(resultGame, 'sum')
        awayPredicted = _getField(resultGame, 'diff')
        print(f'Game {gameId}. Actual results: home {homeScore} - away {awayScore}. '
            f'Actual: sum {actualSum} - diff {actualDiff}. '
            f'Predicted results: sum {sumPredicted} - diff {awayPredicted}')

def runSimulation(settings: SimulationSettings) -> None:
    startTime = time.time()
    if not re.match('^\d\d\d\d-\d\d-\d\d$', settings.cutoff):
        print(f'--cutoff argument value is not valid. Expected a YYYY-MM-DD format')
        return

    print(f'Loading prediction matches starting from {settings.cutoff}')
    predictionsFull = _loadPredictions(settings)
    predictions = []
    for prediction in predictionsFull:
        predictions.append({
            'date': prediction['date'],
            'homeTeam': prediction['homeTeam'],
            'awayTeam': prediction['awayTeam'],
            'gameId': prediction['gameId']
        })
    predictions = pandas.DataFrame(predictions, columns=['gameId', 'date', 'homeTeam', 'awayTeam', 'sum', 'diff'])

    dataLoader = NbaDataLoader(settings)

    print('Starting call to user defined function')
    settings.predict(predictions, dataLoader)
    print('User defined function completed')
    result = predictions.to_dict('records')
    result = _sanitizeResult(result, predictionsFull)
    _displayPredictionsAndResults(result, predictionsFull)

    if settings.resultpath is not None:
        print('Writing result...')
        resultfile = open(settings.resultpath, 'w')
        resultfile.write(json.dumps(result))
        resultfile.close()

    elapsedSeconds = time.time() - startTime
    print(f'Completed in {elapsedSeconds} seconds')