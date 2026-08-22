// Functions for the <see cref="AwincNonFile"/> class to manage average
// wage increases stored in static arrays.

// $Id: awincnf.cpp 1.93 7/6/2026 07:57:02 Olson,DavidJ. $

#include <algorithm>
#include "AwincNonFile.h"
#include "avgwg.h"
#include "Resource.h"
#include "AssumptionType.h"
#include "BaseYearNonFile.h"
#include "oactcnst.h"

using namespace std;

// <remarks>Historical average wage increases, 1978-2024.
// When updating in November, add a value to this array.</remarks>
const double AwincNonFile::awincHist[] = {
                         7.941048,  8.747891,  9.007392,
  10.066281,  5.505224,  4.871540,  5.878443,  4.260533,
   2.968106,  6.377448,  4.925132,  3.959390,  4.619158,
   3.726559,  5.152396,  0.860023,  2.683910,  4.008373,
   4.890539,  5.835092,  5.233866,  5.572834,  5.529993,
   2.385645,  1.002888,  2.444538,  4.648767,  3.659027,
   4.596306,  4.538179,  2.300406, -1.508069,  2.363503,
   3.133333,  3.122550,  1.278133,  3.549622,  3.479039,
   1.130011,  3.453260,  3.624486,  3.747550,  2.825527,
   8.891955,  5.315817,  4.430855,  4.840413
};

// <remarks>Titles for 2026 Trustees Report.</remarks>
const std::string AwincNonFile::titletrOriginal[NUMASSUMSETS] = {
  "2026 Trustees Report Alternative I",
  "2026 Trustees Report Alternative II",
  "2026 Trustees Report Alternative III",
  "No increase beyond 2024 average wage"
};

// <remarks>Average wage increases for 2026 Trustees Report,
//  years 2025-2040.</remarks>
const double AwincNonFile::awincprojtrOriginal[NUMASSUMSETS][NUMPROJYEARS] = {
  {                                         2.961591,
    5.472478, 5.327177, 5.579275, 5.594002, 5.669673,
    5.711974, 5.749210, 5.676113, 5.503555, 5.387438,
    4.957441, 4.907430, 4.909721, 4.919727, 4.899386
  },
  {                                         3.118979,
    4.472929, 4.040337, 4.152047, 4.305250, 4.524713,
    4.521374, 4.384810, 4.223304, 3.917431, 3.826215,
    3.711205, 3.651127, 3.655820, 3.666069, 3.645189
  },
  {                                         3.186556,
    2.737849, 0.644104, 3.079288, 3.251277, 3.680174,
    3.702803, 3.527239, 3.078826, 2.807205, 2.704462,
    2.511288, 2.400906, 2.407478, 2.418425, 2.397180
  },
  {                     0.0,
    0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0, 0.0
  }
};

// <summary>Ultimate average wage increases for 2026 Trustees Report.</summary>
const double AwincNonFile::awincult[NUMASSUMSETS] = {
   4.8, 3.6, 2.3, 0.0
};

/// <summary>Initializes projected average wage increase info with latest
/// Trustees Report assumptions.</summary>
///
/// <param name="newIstart">Starting year of average wage increases.</param>
/// <param name="newMaxyear">Maximum projected year.</param>
AwincNonFile::AwincNonFile( int newIstart, int newMaxyear ) :
AwincDoc(newIstart, newMaxyear)
{
  // Set last year of projected average wage increases, inclusive of
  // YEAR - 1.
  const int LASTYEAR = BaseYearNonFile::YEAR + NUMPROJYEARS - 2;
  // ensure bounds are great enough to hold data</summary>
  const int YEAR78 = YEAR79 - 1;
  const int yr1 = min(YEAR78, newIstart);
  const int yr2 = max(LASTYEAR, newMaxyear);
  for (int i = 0; i < NUMASSUMSETS; i++) {
    awincprojtr[i] = new DoubleAnnual(yr1, yr2);
    DoubleAnnual& temp = *awincprojtr[i];
    // Set historical data
    for (int year = YEAR78; year < BaseYearNonFile::YEAR - 1; year++) {
      temp[year] = awincHist[year - YEAR78];
    }
    // set title and projected values
    read(i+1);
  }
}

/// <summary>Destructor.</summary>
///
/// <remarks>Deletes the vectors of stored Trustees Report assumptions.
/// </remarks>
AwincNonFile::~AwincNonFile()
{
  for (int i = 0; i < NUMASSUMSETS; i++) {
    delete awincprojtr[i];
  }
}

/// <summary>Restore values to original values.</summary>
///
/// <exception cref="PiaException">Thrown if there is any error restoring
/// values to original values.</exception>
/// <param name="altNum">Desired alternative number (1-4).</param>
void AwincNonFile::read( int altNum )
{
  try {
    // set title
    titletr[altNum - 1] = titletrOriginal[altNum - 1];
    // Set last year of projected average wage increases, inclusive of YEAR
    const int LASTYEAR = BaseYearNonFile::YEAR + NUMPROJYEARS - 2;
    // set values in short-range
    DoubleAnnual& temp = *awincprojtr[altNum - 1];
    for (int year = BaseYearNonFile::YEAR - 1; year <= LASTYEAR; year++) {
      temp[year] =
        awincprojtrOriginal[altNum - 1][year - BaseYearNonFile::YEAR + 1];
    }
    // set values in long-range
    for (int year = LASTYEAR + 1; year <= temp.getLastYear(); year++) {
      temp[year] = awincult[altNum - 1];
    }
  } catch (PiaException& e) {
    throw PiaException(string("In AwincNonFile::read: ") + e.what());
  }
}

/// <summary>Dummy function.</summary>
void AwincNonFile::write( int )
{ }

/// <summary>Sets data for one alternative, using the stored data for the
/// specified alternative.</summary>
///
/// <param name="altNum">Desired alternative number (1-7).</param>
void AwincNonFile::setData( int altNum )
{
  const int i1 = max(getFirstYear(), awinc.getBaseYear());
  if (AssumptionType::isTR(altNum)) {
    awinc.assign(*awincprojtr[altNum - 1], i1, awinc.getLastYear());
  }
  else {
    awinc.assign(0.0, i1, awinc.getLastYear());
  }
}

/// <summary>Sets data for one alternative, storing the data for the specified
/// alternative, then setting the current data to that data.</summary>
///
/// <param name="altNum">Desired alternative number (1-7).</param>
/// <param name="newData">Data to use.</param>
void AwincNonFile::setData( int altNum, const DoubleAnnual& newData )
{
  if (AssumptionType::isTR(altNum)) {
    awincprojtr[altNum - 1]->assign(newData, getFirstYear(),
      awincprojtr[altNum - 1]->getLastYear());
  }
  setData(altNum);
}

/// <summary>Sets the current title, using the title stored for the specified
/// alternative.</summary>
///
/// <param name="altNum">Desired alternative number (1-7).</param>
void AwincNonFile::setTitle( int altNum )
{
  if (AssumptionType::isNotTR(altNum)) {
    awincTitle = avgwage[altNum - AssumptionType::FLAT];
  }
  else {
    awincTitle = titletr[altNum - 1];
  }
}

/// <summary>Sets the current title, storing the title for the specified
/// alternative, then setting the current title to that title.</summary>
///
/// <param name="altNum">Desired alternative number (1-7).</param>
/// <param name="newTitle">Title to use.</param>
void AwincNonFile::setTitle( int altNum, const std::string& newTitle )
{
  if (AssumptionType::isNotTR(altNum)) {
    awincTitle = avgwage[altNum - AssumptionType::FLAT];
  }
  else {
    titletr[altNum - 1] = newTitle;
    awincTitle = titletr[altNum - 1];
  }
}
