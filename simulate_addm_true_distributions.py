#!/usr/bin/python

"""
simulate_addm_true_distributions.py
Author: Gabriela Tavares, gtavares@caltech.edu

Generates aDDM simulations with an approximation of the "true" fixation
distributions. When creating fixation distributions, we leave out the last
fixation from each trial, since these are interrupted when a decision is made
and therefore their duration should not be sampled. Since long fixations are
more likely to be interrupted, they end up not being included in the
distributions. THis means that the distributions we use to sample fixations are
biased towards shorter fixations than the "true" distributions. Here we use the
uninterrupted duration of last fixations to approximate the "true" distributions
of fixations. We do this by dividing each bin in the empirical fixation
distributions by the probability of a fixation in that bin being the last
fixation in the trial. The "true" distributions estimated are then used to
generate aDDM simulations.  
"""

from multiprocessing import Pool

import collections
import numpy as np
import pandas as pd
import sys

from addm import get_empirical_distributions
from util import load_data_from_csv, save_simulations_to_csv


def run_simulations(probLeftFixFirst, distLatencies, distTransitions,
                    distFixations, numTrials, trialConditions, d, theta, sigma,
                    bins, numFixDists=3, timeStep=10, barrier=1, visualDelay=0,
                    motorDelay=0):
    """
    Generates aDDM simulations given the model parameters and some empirical
    fixation data, which are used to generate the simulated fixations.
    Args:
      probLeftFixFirst: float between 0 and 1, empirical probability that the
          left item will be fixated first.
      distLatencies: numpy array corresponding to the empirical distribution of
          trial latencies (delay before first fixation) in miliseconds.
      distTransitions: numpy array corresponding to the empirical distribution
          of transitions (delays between item fixations) in miliseconds.
      distFixations: dict of dicts of dicts, corresponding to the probability
          distributions of fixation durations. Indexed first by fixation type
          (1st, 2nd, etc), then by the value difference between the fixated and
          the unfixated items, then by time bin. Each entry is a number between
          0 and 1 corresponding to the probability assigned to the particular
          time bin (i.e. given a particular fixation type and value difference,
          probabilities for all bins should add up to 1).
      numTrials: integer, number of simulations to be generated for each trial
          condition.
      trialConditions: list of tuples, where each entry is a pair (valueLeft,
          valueRight), containing the values of the two items.
      d: float, parameter of the model which controls the speed of integration
          of the signal.
      theta: float between 0 and 1, parameter of the model which controls the
          attentional bias.
      sigma: float, parameter of the model, standard deviation for the normal
          distribution.
      bins: list containing the time bins used in distFixations.
      numFixDists: integer, number of fixation types to use in the fixation
          distributions. For instance, if numFixDists equals 3, then 3 separate
          fixation types will be used, corresponding to the 1st, 2nd and other
          (3rd and up) fixations in each trial.
      timeStep: integer, value in miliseconds to be used for binning the time
          axis.
      barrier: positive number, magnitude of the signal thresholds.
      visualDelay: delay to be discounted from the beginning of all fixations,
          in miliseconds.
      motorDelay: delay to be discounted from the last fixation only, in
          miliseconds.
    """

    # Simulation data to be returned.
    RT = dict()
    choice = dict()
    valueLeft = dict()
    valueRight = dict()
    fixItem = dict()
    fixTime = dict()
    fixRDV = dict()
    uninterruptedLastFixTime = dict()

    trialCount = 0

    for trialCondition in trialConditions:
        vLeft = trialCondition[0]
        vRight = trialCondition[1]
        fixUnfixValueDiffs = {1: vLeft - vRight, 2: vRight - vLeft}
        trial = 0
        while trial < numTrials:
            fixItem[trialCount] = list()
            fixTime[trialCount] = list()
            fixRDV[trialCount] = list()

            RDV = 0
            trialTime = 0

            # Sample and iterate over the latency for this trial.
            trialAborted = False
            while True:
                latency = np.random.choice(distLatencies)
                for t in xrange(int(latency // timeStep)):
                    # Sample the change in RDV from the distribution.
                    RDV += np.random.normal(0, sigma)
                    # If the RDV hit one of the barriers, we abort the trial,
                    # since a trial must end on an item fixation.
                    if RDV >= barrier or RDV <= -barrier:
                        trialAborted = True
                        break

                if trialAborted:
                    RDV = 0
                    trialAborted = False
                    continue
                else:
                    # Add latency to this trial's data.
                    fixRDV[trialCount].append(RDV)
                    fixItem[trialCount].append(0)
                    fixTime[trialCount].append(latency - (latency % timeStep))
                    trialTime += latency - (latency % timeStep)
                    break

            # Sample the first fixation for this trial.
            probLeftRight = np.array([probLeftFixFirst, 1 - probLeftFixFirst])
            currFixItem = np.random.choice([1, 2], p=probLeftRight)
            valueDiff = fixUnfixValueDiffs[currFixItem]
            prob = ([value for (key, value) in
                    sorted(distFixations[1][valueDiff].items())])
            currFixTime = np.random.choice(bins, p=prob) - visualDelay

            # Iterate over all fixations in this trial.
            fixNumber = 2
            trialFinished = False
            trialAborted = False
            while True:
                # Iterate over the visual delay for the current fixation.
                for t in xrange(int(visualDelay // timeStep)):
                    # Sample the change in RDV from the distribution.
                    RDV += np.random.normal(0, sigma)

                    # If the RDV hit one of the barriers, the trial is over.
                    if RDV >= barrier or RDV <= -barrier:
                        if RDV >= barrier:
                            choice[trialCount] = -1
                        elif RDV <= -barrier:
                            choice[trialCount] = 1
                        valueLeft[trialCount] = vLeft
                        valueRight[trialCount] = vRight
                        fixRDV[trialCount].append(RDV)
                        fixItem[trialCount].append(currFixItem)
                        fixTime[trialCount].append(
                            ((t + 1) * timeStep) + motorDelay)
                        trialTime += ((t + 1) * timeStep) + motorDelay
                        RT[trialCount] = trialTime
                        uninterruptedLastFixTime[trialCount] = currFixTime
                        trialFinished = True
                        break

                if trialFinished:
                    break

                # Iterate over the time interval of the current fixation.
                for t in xrange(int(currFixTime // timeStep)):
                    # We use a distribution to model changes in RDV
                    # stochastically. The mean of the distribution (the change
                    # most likely to occur) is calculated from the model
                    # parameters and from the values of the two items.
                    if currFixItem == 1:  # Subject is looking left.
                        mean = d * (vLeft - (theta * vRight))
                    elif currFixItem == 2:  # Subject is looking right.
                        mean = d * (-vRight + (theta * vLeft))

                    # Sample the change in RDV from the distribution.
                    RDV += np.random.normal(mean, sigma)

                    # If the RDV hit one of the barriers, the trial is over.
                    if RDV >= barrier or RDV <= -barrier:
                        if RDV >= barrier:
                            choice[trialCount] = -1
                        elif RDV <= -barrier:
                            choice[trialCount] = 1
                        valueLeft[trialCount] = vLeft
                        valueRight[trialCount] = vRight
                        fixRDV[trialCount].append(RDV)
                        fixItem[trialCount].append(currFixItem)
                        fixTime[trialCount].append(
                            ((t + 1) * timeStep) + visualDelay + motorDelay)
                        trialTime += (((t + 1) * timeStep) + visualDelay +
                                      motorDelay)
                        RT[trialCount] = trialTime
                        uninterruptedLastFixTime[trialCount] = currFixTime
                        trialFinished = True
                        break

                if trialFinished:
                    break

                # Add previous fixation to this trial's data.
                fixRDV[trialCount].append(RDV)
                fixItem[trialCount].append(currFixItem)
                fixTime[trialCount].append(
                    (currFixTime - (currFixTime % timeStep)) + visualDelay)
                trialTime += ((currFixTime - (currFixTime % timeStep)) + 
                              visualDelay)

                # Sample and iterate over transition.
                transition = np.random.choice(distTransitions)
                for t in xrange(int(transition // timeStep)):
                    # Sample the change in RDV from the distribution.
                    RDV += np.random.normal(0, sigma)

                    # If the RDV hit one of the barriers, we abort the trial,
                    # since a trial must end on an item fixation.
                    if RDV >= barrier or RDV <= -barrier:
                        trialFinished = True
                        trialAborted = True
                        break

                if trialFinished:
                    break

                # Add previous transition to this trial's data.
                fixRDV[trialCount].append(RDV)
                fixItem[trialCount].append(0)
                fixTime[trialCount].append(transition - (transition % timeStep))
                trialTime += transition - (transition % timeStep)

                # Sample the next fixation for this trial.
                if currFixItem == 1:
                    currFixItem = 2
                elif currFixItem == 2:
                    currFixItem = 1
                valueDiff = fixUnfixValueDiffs[currFixItem]
                prob = ([value for (key, value) in
                        sorted(distFixations[fixNumber][valueDiff].items())])
                currFixTime = np.random.choice(bins, p=prob) - visualDelay
                if fixNumber < numFixDists:
                    fixNumber += 1

            # Move on to the next trial.
            if not trialAborted:
                trial += 1
                trialCount += 1

    simul = collections.namedtuple(
        'Simul', ['RT', 'choice', 'valueLeft', 'valueRight', 'fixItem',
        'fixTime', 'fixRDV', 'uninterruptedLastFixTime'])
    return simul(RT, choice, valueLeft, valueRight, fixItem, fixTime, fixRDV,
                 uninterruptedLastFixTime)


def main():
    # Time bins to be used in the fixation distributions.
    binStep = 10
    bins = range(binStep, 3000 + binStep, binStep)

    numFixDists = 3  # Number of fixation distributions.
    N = 2  # Number of iterations to approximate true distributions.

    # Load experimental data from CSV file.
    data = load_data_from_csv("expdata.csv", "fixations.csv",
                              useAngularDists=True)
    RT = data.RT
    choice = data.choice
    valueLeft = data.valueLeft
    valueRight = data.valueRight
    fixItem = data.fixItem
    fixTime = data.fixTime

    # Get empirical distributions.
    dists = get_empirical_distributions(
        valueLeft, valueRight, fixItem, fixTime, useOddTrials=False,
        useEvenTrials=True)
    probLeftFixFirst = dists.probLeftFixFirst
    distLatencies = dists.distLatencies
    distTransitions = dists.distTransitions
    distFixations = dists.distFixations

    # Parameters for generating simulations.
    d = 0.004
    sigma = 0.07
    theta = 0.25
    numTrials = 400
    orientations = range(-15,20,5)
    trialConditions = list()
    for oLeft in orientations:
        for oRight in orientations:
            if oLeft != oRight:
                vLeft = np.absolute((np.absolute(oLeft) - 15) / 5)
                vRight = np.absolute((np.absolute(oRight) - 15) / 5)
                trialConditions.append((vLeft, vRight))

    # Create original empirical distributions of fixations.
    empiricalFixDist = dict()
    for numFix in xrange(1, numFixDists + 1):
        empiricalFixDist[numFix] = dict()
        for valueDiff in xrange(-3,4):
            empiricalFixDist[numFix][valueDiff] = dict()
            for bin in bins:
                empiricalFixDist[numFix][valueDiff][bin] = 0
            for fixTime in distFixations[numFix][valueDiff]:
                bin = binStep * min((fixTime // binStep) + 1, len(bins))
                empiricalFixDist[numFix][valueDiff][bin] += 1

    # Normalize the distributions.
    for numFix in xrange(1, numFixDists + 1):
        for valueDiff in xrange(-3,4):
            sumBins = sum(empiricalFixDist[numFix][valueDiff].values())
            for bin in bins:
                empiricalFixDist[numFix][valueDiff][bin] = (
                    float(empiricalFixDist[numFix][valueDiff][bin]) /
                    float(sumBins))

    # Repeat the process N times.
    for i in xrange(N):
        # Generate simulations using the current empirical distributions and the
        # model parameters.
        simul = run_simulations(
            probLeftFixFirst, distLatencies, distTransitions, empiricalFixDist,
            numTrials, trialConditions, d, theta, sigma, bins, numFixDists)
        simulRT = simul.RT
        simulChoice = simul.choice
        simulValueLeft = simul.valueLeft
        simulValueRight = simul.valueRight
        simulFixItem = simul.fixItem
        simulFixTime = simul.fixTime
        simulFixRDV = simul.fixRDV
        simulUninterruptedLastFixTime = simul.uninterruptedLastFixTime

        countLastFix = dict()
        countTotal = dict()
        for numFix in xrange(1, numFixDists + 1):
            countLastFix[numFix] = dict()
            countTotal[numFix] = dict()
            for valueDiff in xrange(-3,4):
                countLastFix[numFix][valueDiff] = dict()
                countTotal[numFix][valueDiff] = dict()
                for bin in bins:
                    countLastFix[numFix][valueDiff][bin] = 0
                    countTotal[numFix][valueDiff][bin] = 0

        for trial in simulRT.keys():
            # Count all item fixations, except last.
            fixUnfixValueDiffs = {
                1: simulValueLeft[trial] - simulValueRight[trial],
                2: simulValueRight[trial] - simulValueLeft[trial]}
            numFix = 1
            for item, time in zip(simulFixItem[trial][:-1],
                simulFixTime[trial][:-1]):
                if item == 1 or item == 2:
                    bin = binStep * min((time // binStep) + 1, len(bins))
                    vDiff = fixUnfixValueDiffs[item]
                    countTotal[numFix][vDiff][bin] += 1
                    if numFix < numFixDists:
                        numFix += 1
            # Count last fixation.
            item = simulFixItem[trial][-1]
            vDiff = fixUnfixValueDiffs[item]
            bin = binStep * min(
                (simulUninterruptedLastFixTime[trial] // binStep) + 1,
                len(bins))
            countLastFix[numFix][vDiff][bin] += 1
            countTotal[numFix][vDiff][bin] += 1

        # Obtain true distributions of fixations.
        trueFixDist = dict()
        for numFix in xrange(1, numFixDists + 1):
            trueFixDist[numFix] = dict()
            for valueDiff in xrange(-3,4):
                trueFixDist[numFix][valueDiff] = dict()
                for bin in bins:
                    probNotLastFix = 1
                    if countTotal[numFix][valueDiff][bin] > 0:
                        probNotLastFix = 1 - (
                            float(countLastFix[numFix][valueDiff][bin]) /
                            float(countTotal[numFix][valueDiff][bin]))
                    if probNotLastFix == 0:
                        trueFixDist[numFix][valueDiff][bin] = (
                            empiricalFixDist[numFix][valueDiff][bin])
                    else:
                        trueFixDist[numFix][valueDiff][bin] = (
                            float(empiricalFixDist[numFix][valueDiff][bin]) /
                            float(probNotLastFix))
        # Normalize the distributions.
        for numFix in xrange(1, numFixDists + 1):
            for valueDiff in xrange(-3,4):
                sumBins = sum(trueFixDist[numFix][valueDiff].values())
                if sumBins > 0:
                    for bin in bins:
                        trueFixDist[numFix][valueDiff][bin] = (
                            float(trueFixDist[numFix][valueDiff][bin]) /
                            float(sumBins))

        # Update empirical distributions using the current true distributions.
        empiricalFixDist = trueFixDist

    # Generate final simulations.
    simul = run_simulations(
        probLeftFixFirst, distLatencies, distTransitions, empiricalFixDist,
        numTrials, trialConditions, d, theta, sigma, bins, numFixDists)
    simulRT = simul.RT
    simulChoice = simul.choice
    simulValueLeft = simul.valueLeft
    simulValueRight = simul.valueRight
    simulFixItem = simul.fixItem
    simulFixTime = simul.fixTime
    simulFixRDV = simul.fixRDV
    simulUninterruptedLastFixTime = simul.uninterruptedLastFixTime

    totalTrials = numTrials * len(trialConditions)
    save_simulations_to_csv(
        simulChoice, simulRT, simulValueLeft, simulValueRight, simulFixItem,
        simulFixTime, simulFixRDV, totalTrials)


if __name__ == '__main__':
    main()