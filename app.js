// ================= PARTEA 2: RATINGURI REALE CLUBURI + MOTOR ANALIZĂ CALIBRAT PE COTE (FIXED) =================

const CLUB_POWER = [
  {k:"manchester city",p:0.55},{k:"real madrid",p:0.55},{k:"bayern",p:0.54},{k:"barcelona",p:0.52},
  {k:"liverpool",p:0.50},{k:"inter",p:0.48},{k:"arsenal",p:0.48},{k:"paris saint-germain",p:0.48},{k:"psg",p:0.48},
  {k:"leverkusen",p:0.42},{k:"napoli",p:0.44},{k:"atletico",p:0.40},{k:"atlético",p:0.40},{k:"dortmund",p:0.38},
  {k:"juventus",p:0.38},{k:"milan",p:0.36},{k:"atalanta",p:0.39},{k:"chelsea",p:0.36},{k:"tottenham",p:0.32},
  {k:"aston villa",p:0.31},{k:"newcastle",p:0.30},{k:"manchester united",p:0.26},{k:"leipzig",p:0.34},
  {k:"sporting",p:0.44},{k:"benfica",p:0.42},{k:"porto",p:0.40},{k:"psv",p:0.44},{k:"feyenoord",p:0.34},{k:"ajax",p:0.32},
  {k:"galatasaray",p:0.42},{k:"fenerbahce",p:0.40},{k:"fenerbahçe",p:0.40},{k:"besiktas",p:0.28},
  {k:"olympiacos",p:0.34},{k:"paok",p:0.31},{k:"panathinaikos",p:0.29},{k:"aek",p:0.29},
  {k:"lazio",p:0.30},{k:"roma",p:0.29},{k:"fiorentina",p:0.27},{k:"bologna",p:0.20},{k:"torino",p:0.12},
  {k:"athletic",p:0.28},{k:"villarreal",p:0.27},{k:"real sociedad",p:0.24},{k:"betis",p:0.22},{k:"girona",p:0.18},
  {k:"frankfurt",p:0.27},{k:"stuttgart",p:0.27},{k:"monaco",p:0.32},{k:"marseille",p:0.31},{k:"lille",p:0.28},{k:"lyon",p:0.25},
  {k:"brighton",p:0.22},{k:"fulham",p:0.15},{k:"bournemouth",p:0.14},{k:"west ham",p:0.14},{k:"braga",p:0.25},
  {k:"fcsb",p:0.32},{k:"cfr cluj",p:0.28},{k:"universitatea craiova",p:0.26},{k:"craiova",p:0.26},
  {k:"universitatea cluj",p:0.22},{k:"u cluj",p:0.22},{k:"rapid",p:0.22},{k:"dinamo",p:0.16},{k:"sepsi",p:0.12},{k:"farul",p:0.10},
  {k:"slobozia",p:-0.24},{k:"botoșani",p:-0.20},{k:"botosani",p:-0.20},{k:"buzău",p:-0.25},{k:"buzau",p:-0.25},{k:"poli iași",p:-0.18},{k:"ermannstadt",p:-0.10},
  {k:"monza",p:-0.26},{k:"lecce",p:-0.26},{k:"venezia",p:-0.28},{k:"empoli",p:-0.20},{k:"cagliari",p:-0.20},
  {k:"verona",p:-0.22},{k:"parma",p:-0.16},{k:"como",p:-0.14},{k:"genoa",p:-0.16},{k:"udinese",p:-0.06},{k:"sassuolo",p:-0.12},
  {k:"valladolid",p:-0.28},{k:"las palmas",p:-0.24},{k:"leganes",p:-0.22},{k:"espanyol",p:-0.22},{k:"getafe",p:-0.14},{k:"alaves",p:-0.18},
  {k:"southampton",p:-0.30},{k:"ipswich",p:-0.28},{k:"leicester",p:-0.24},{k:"wolves",p:-0.18},{k:"everton",p:-0.14},{k:"crystal palace",p:-0.08},
  {k:"kiel",p:-0.28},{k:"bochum",p:-0.28},{k:"st. pauli",p:-0.24},{k:"heidenheim",p:-0.20},{k:"augsburg",p:-0.14},
  {k:"le havre",p:-0.26},{k:"angers",p:-0.26},{k:"montpellier",p:-0.24},{k:"saint-etienne",p:-0.22},{k:"nantes",p:-0.18},{k:"auxerre",p:-0.16}
];

function getClubBasePower(name) {
  const low = (name || "").toLowerCase();
  for (let c of CLUB_POWER) if (low.includes(c.k)) return c.p;
  return 0;
}

function extractTeamStrength(compObj, isHome, teamName) {
  let formScore = 0, overallScore = 0, venueScore = 0, formDisplay = "";
  let winsRate5 = 2.0, drawsRate5 = 1.4, lossesRate5 = 1.6, drawRatio = 0.26;
  let hasRealRecord = false, hasRealForm = false;

  const clubPower = getClubBasePower(teamName || (compObj.team && (compObj.team.displayName || compObj.team.name)) || "");

  if (compObj.records && Array.isArray(compObj.records)) {
    const parseRec = (rec) => {
      if (!rec || !rec.summary) return null;
      const parts = rec.summary.split("-").map(x => parseInt(x, 10));
      if (parts.length === 3 && !isNaN(parts[0])) {
        const [w, d, l] = parts;
        const tot = w + d + l;
        if (tot > 0) return { w, d, l, tot, ppg: (w * 3 + d) / tot };
      }
      return null;
    };

    const totalRec = parseRec(compObj.records.find(r => r.type === "total") || compObj.records[0]);
    const venueRec = parseRec(compObj.records.find(r => 
      r.type === (isHome ? "home" : "road") || 
      (r.name && r.name.toLowerCase() === (isHome ? "home" : "away"))
    ));

    if (totalRec) {
      hasRealRecord = true;
      const reliability = Math.min(1.0, totalRec.tot / (totalRec.tot + 3));
      overallScore = (totalRec.ppg - 1.35) * 0.62 * reliability;
      formDisplay = `${totalRec.w}V-${totalRec.d}E-${totalRec.l}Î`;
      winsRate5 = (totalRec.w / totalRec.tot) * 5;
      drawsRate5 = (totalRec.d / totalRec.tot) * 5;
      lossesRate5 = (totalRec.l / totalRec.tot) * 5;
      drawRatio = totalRec.d / totalRec.tot;
    }

    if (venueRec && venueRec.tot >= 2) {
      const venueRel = Math.min(1.0, venueRec.tot / (venueRec.tot + 3));
      const expectedVenuePpg = isHome ? 1.50 : 1.20;
      venueScore = (venueRec.ppg - expectedVenuePpg) * 0.50 * venueRel;
    }
  }

  if (compObj.form && typeof compObj.form === "string") {
    const rawForm = compObj.form.toUpperCase().replace(/[^WDL]/g, "").slice(-5);
    if (rawForm.length >= 3) {
      hasRealForm = true;
      let fW = 0, fD = 0, fL = 0;
      formDisplay = formDisplay ? `${rawForm} (${formDisplay})` : rawForm;
      const weights = [0.60, 0.80, 1.0, 1.25, 1.50];
      for (let i = 0; i < rawForm.length; i++) {
        const ch = rawForm[i];
        if (ch === "W") fW++;
        else if (ch === "D") fD++;
        else if (ch === "L") fL++;
        const w = weights[i + (5 - rawForm.length)] || 1.0;
        formScore += (ch === "W" ? 0.075 : (ch === "D" ? 0.0 : -0.075)) * w;
      }
      const scale5 = 5 / rawForm.length;
      if (hasRealRecord) {
        winsRate5 = winsRate5 * 0.50 + (fW * scale5) * 0.50;
        drawsRate5 = drawsRate5 * 0.50 + (fD * scale5) * 0.50;
        lossesRate5 = lossesRate5 * 0.50 + (fL * scale5) * 0.50;
      } else {
        winsRate5 = fW * scale5;
        drawsRate5 = fD * scale5;
        lossesRate5 = fL * scale5;
        drawRatio = fD / rawForm.length;
      }
    }
  }

  const hasData = hasRealRecord || hasRealForm || clubPower !== 0;
  if (!formDisplay) formDisplay = clubPower !== 0 ? "Rating Lot Activ" : "Date limitate";

  let tablePerf = overallScore;
  if (venueScore !== 0) tablePerf = overallScore * 0.62 + venueScore * 0.38;

  let statsStrength = hasRealRecord
    ? (hasRealForm ? tablePerf * 0.68 + formScore * 0.32 : tablePerf)
    : formScore;

  let totalStrength = statsStrength;
  if (clubPower !== 0 && (hasRealRecord || hasRealForm)) {
    totalStrength = statsStrength * 0.45 + clubPower * 0.55;
  } else if (clubPower !== 0) {
    totalStrength = clubPower * 0.85;
  }

  return {
    score: totalStrength,
    clubPower,
    winsCount: +winsRate5.toFixed(2),
    drawsCount: +drawsRate5.toFixed(2),
    lossesCount: +lossesRate5.toFixed(2),
    drawRatio,
    hasData,
    formDisplay
  };
}

function analyzeMatch(ev, lg) {
  const comp = ev.competitions[0], cs = comp.competitors;
  const home = cs.find(c => c.homeAway === "home") || cs[0], away = cs.find(c => c.homeAway === "away") || cs[1];
  const hName = home.team.displayName || home.team.name, aName = away.team.displayName || away.team.name;
  const dt = new Date(comp.date || ev.date), stState = (comp.status && comp.status.type && comp.status.type.state) || "pre";
  const hScore = home.score !== undefined ? parseInt(home.score, 10) : null, aScore = away.score !== undefined ? parseInt(away.score, 10) : null;

  const hHT = (home.linescores && home.linescores.length > 0 && home.linescores[0].value !== undefined) ? parseInt(home.linescores[0].value, 10) : null;
  const aHT = (away.linescores && away.linescores.length > 0 && away.linescores[0].value !== undefined) ? parseInt(away.linescores[0].value, 10) : null;

  const hInfo = extractTeamStrength(home, true, hName);
  const aInfo = extractTeamStrength(away, false, aName);
  const lowData = !hInfo.hasData && !aInfo.hasData;

  const hBoost = hInfo.score;
  const aBoost = aInfo.score;
  const strengthDiff = hBoost - aBoost;

  const isDerby = hBoost >= 0.22 && aBoost >= 0.22 && Math.abs(strengthDiff) <= 0.18;

  const lgGoals = lg.gBase || 2.62;
  // Anulam avantajul terenului propriu dacă oaspeții sunt net superiori ca valoare de lot
  const homeAdvShare = strengthDiff < -0.35 ? 0.460 : (strengthDiff < -0.15 ? 0.490 : (strengthDiff > 0.25 ? 0.555 : 0.525));
  const baseH = lgGoals * homeAdvShare;
  const baseA = lgGoals * (1 - homeAdvShare);
  const paceMod = (0.26 - (hInfo.drawRatio + aInfo.drawRatio) / 2) * 0.45 + (hBoost + aBoost) * 0.16;

  let lamH = Math.max(0.40, Math.min(3.35, baseH + strengthDiff * 1.05 + paceMod * 0.45));
  let lamA = Math.max(0.40, Math.min(3.35, baseA - strengthDiff * 1.05 + paceMod * 0.45));

  const mkt = extractMarketOdds(comp);
  if (mkt && mkt.mktPH && mkt.mktPA && (mkt.mktPH + mkt.mktPA) > 0.2) {
    let targetTotal = lamH + lamA;
    if (mkt.ouLine && mkt.ouLine >= 1.5 && mkt.ouLine <= 4.0) {
      targetTotal = targetTotal * 0.60 + mkt.ouLine * 0.40;
    }
    const mktShareH = Math.max(0.15, Math.min(0.85, mkt.mktPH / (mkt.mktPH + mkt.mktPA)));
    const modShareH = lamH / (lamH + lamA);
    const finalShareH = modShareH * 0.45 + mktShareH * 0.55;
    lamH = Math.max(0.40, Math.min(3.35, targetTotal * finalShareH));
    lamA = Math.max(0.40, Math.min(3.35, targetTotal * (1 - finalShareH)));
  }

  const rho = (lg.rho || -0.09) + (isDerby ? -0.02 : 0);

  let pH = 0, pD = 0, pA = 0, p00 = 0, pO15 = 0, pO25 = 0, pU25 = 0, pGG = 0;
  let p1_O15 = 0, p2_O15 = 0, p1X_O15 = 0, pX2_O15 = 0, p1X_U35 = 0, pX2_U35 = 0;
  let totalProbMass = 0;

  for (let h = 0; h <= 7; h++) {
    for (let a = 0; a <= 7; a++) {
      const rawP = poissonPmf(h, lamH) * poissonPmf(a, lamA) * dixonColesTau(h, a, lamH, lamA, rho);
      totalProbMass += rawP;

      if (h === 0 && a === 0) p00 += rawP;
      if (h > a) pH += rawP;
      else if (h === a) pD += rawP;
      else pA += rawP;

      const goals = h + a;
      if (goals >= 2) pO15 += rawP;
      if (goals >= 3) pO25 += rawP;
      else pU25 += rawP;
      if (h > 0 && a > 0) pGG += rawP;

      if (h > a && goals >= 2) p1_O15 += rawP;
      if (a > h && goals >= 2) p2_O15 += rawP;
      if (h >= a && goals >= 2) p1X_O15 += rawP;
      if (a >= h && goals >= 2) pX2_O15 += rawP;
      if (h >= a && goals <= 3) p1X_U35 += rawP;
      if (a >= h && goals <= 3) pX2_U35 += rawP;
    }
  }

  pH /= totalProbMass; pD /= totalProbMass; pA /= totalProbMass; p00 /= totalProbMass;
  pO15 /= totalProbMass; pO25 /= totalProbMass; pU25 /= totalProbMass; pGG /= totalProbMass;
  p1_O15 /= totalProbMass; p2_O15 /= totalProbMass;
  p1X_O15 /= totalProbMass; pX2_O15 /= totalProbMass;
  p1X_U35 /= totalProbMass; pX2_U35 /= totalProbMass;

  const p1X = pH + pD;
  const pX2 = pA + pD;

  const nonZeroDraw = Math.max(0, pD - p00);
  const pPSF1 = Math.min(0.85, pH + nonZeroDraw * 0.34 + pA * 0.06);
  const pPSF2 = Math.min(0.83, pA + nonZeroDraw * 0.34 + pH * 0.06);

  const totalXG = lamH + lamA;
  const xgDiff = lamH - lamA;

  const candidates = [];

  const addCandidate = (name, mktType, prob, realOdd, specificityWeight) => {
    const fairOdd = 1 / Math.max(0.15, prob);
    const displayOdd = realOdd ? +realOdd.toFixed(2) : +(0.93 * fairOdd).toFixed(2);
    if (displayOdd < 1.33 || displayOdd > 2.35 || prob < 0.50) return;

    const edgePct = realOdd ? Math.round((prob * realOdd - 1) * 100) : 0;
    const edgeBonus = (realOdd && edgePct > 0) ? Math.min(0.08, edgePct * 0.008) : 0;
    const valueScore = prob * specificityWeight + edgeBonus;
    candidates.push({ name, mktType, prob, odd: displayOdd, edgePct, valueScore });
  };

  // 1. Soliști (1 / 2)
  if (pH >= 0.48) addCandidate(`1 (${hName})`, "SOLO", pH, mkt?.decH, 1.10);
  if (pA >= 0.48) addCandidate(`2 (${aName})`, "SOLO", pA, mkt?.decA, 1.10);

  // 2. Solist & Peste 1.5 Goluri
  if (pH >= 0.62 && p1_O15 >= 0.53) addCandidate(`1 & Peste 1.5 Goluri`, "COMBO_SOLO", p1_O15, null, 1.07);
  if (pA >= 0.60 && p2_O15 >= 0.52) addCandidate(`2 & Peste 1.5 Goluri`, "COMBO_SOLO", p2_O15, null, 1.07);

  // 3. Piețe de goluri
  if (pO25 >= 0.53 && totalXG >= 2.62) addCandidate("Peste 2.5 Goluri", "O25", pO25, null, 1.06);
  if (pGG >= 0.54 && lamH >= 1.12 && lamA >= 1.02) addCandidate("GG (Ambele marchează)", "GG", pGG, null, 1.05);
  if (pU25 >= 0.56 && totalXG <= 2.26) addCandidate("Sub 2.5 Goluri", "U25", pU25, null, 1.04);

  // 4. Combo Șansă Dublă & Goluri (interzise dacă echipa are xG negativ sau e net inferioară)
  if (xgDiff >= 0.18 && p1X_O15 >= 0.55 && totalXG >= 2.42) addCandidate("1X & Peste 1.5 Goluri", "COMBO_DC", p1X_O15, null, 1.04);
  if (xgDiff <= -0.18 && pX2_O15 >= 0.54 && totalXG >= 2.42) addCandidate("X2 & Peste 1.5 Goluri", "COMBO_DC", pX2_O15, null, 1.04);
  if (xgDiff >= 0.14 && p1X_U35 >= 0.57 && totalXG <= 2.50) addCandidate("1X & Sub 3.5 Goluri", "COMBO_U35", p1X_U35, null, 1.01);
  if (xgDiff <= -0.14 && pX2_U35 >= 0.57 && totalXG <= 2.50) addCandidate("X2 & Sub 3.5 Goluri", "COMBO_U35", pX2_U35, null, 1.01);

  // 5. Pauză sau Final
  if (pH >= 0.42 && pH <= 0.52 && xgDiff >= 0.15) addCandidate(`PSF 1 (${hName})`, "PSF", pPSF1, null, 0.99);
  if (pA >= 0.42 && pA <= 0.52 && xgDiff <= -0.15) addCandidate(`PSF 2 (${aName})`, "PSF", pPSF2, null, 0.99);

  // 6. Peste 1.5 / Șansă Dublă pură (Interzis 1X dacă oaspeții sunt favoriti clari!)
  if (pO15 >= 0.62 && pO15 <= 0.69) addCandidate("Peste 1.5 Goluri", "O15", pO15, null, 0.94);
  if (xgDiff >= 0.12 && p1X >= 0.58 && p1X <= 0.69) addCandidate("Șansă Dublă 1X", "DC", p1X, null, 0.92);
  if (xgDiff <= -0.12 && pX2 >= 0.58 && pX2 <= 0.69) addCandidate("Șansă Dublă X2", "DC", pX2, null, 0.92);

  if (!candidates.length) {
    if (pH >= pA && pH >= 0.44) candidates.push({ name: `1 (${hName})`, mktType: "SOLO", prob: pH, odd: +(0.93 / pH).toFixed(2), edgePct: 0, valueScore: pH });
    else if (pA > pH && pA >= 0.44) candidates.push({ name: `2 (${aName})`, mktType: "SOLO", prob: pA, odd: +(0.93 / pA).toFixed(2), edgePct: 0, valueScore: pA });
    else if (xgDiff < 0) candidates.push({ name: "Șansă Dublă X2", mktType: "DC", prob: pX2, odd: Math.max(1.25, +(0.92 / pX2).toFixed(2)), edgePct: 0, valueScore: pX2 * 0.9 });
    else candidates.push({ name: "Șansă Dublă 1X", mktType: "DC", prob: p1X, odd: Math.max(1.25, +(0.92 / p1X).toFixed(2)), edgePct: 0, valueScore: p1X * 0.9 });
  }

  candidates.sort((a, b) => b.valueScore - a.valueScore);
  const best = candidates[0];

  const getStat = (compObj, names) => {
    if (!compObj.statistics) return null;
    for (let n of names) {
      const f = compObj.statistics.find(s => s.name === n || s.abbreviation === n);
      if (f && f.displayValue !== undefined) {
        const val = parseFloat(f.displayValue);
        if (!isNaN(val)) return val;
      }
    }
    return null;
  };

  const realHCorners = getStat(home, ["wonCorners", "cornerKicks", "corners", "CK"]);
  const realACorners = getStat(away, ["wonCorners", "cornerKicks", "corners", "CK"]);
  const realHYellow = getStat(home, ["yellowCards", "YC"]);
  const realAYellow = getStat(away, ["yellowCards", "YC"]);
  const realHRed = getStat(home, ["redCards", "RC"]) || 0;
  const realARed = getStat(away, ["redCards", "RC"]) || 0;

  const offensiveMomentum = ((hInfo.winsCount + aInfo.winsCount) - 3.8) * 0.28;
  const openPlayFactor = (0.26 - (hInfo.drawRatio + aInfo.drawRatio) / 2) * 2.4;
  const mismatchPressure = Math.abs(lamH - lamA) * 0.65;
  const derbyCornerPush = isDerby ? 0.50 : 0;

  const expCornersNum = Math.max(7.2, Math.min(12.6, 
    (lg.cBase || 9.5) + (totalXG - (lg.gBase || 2.62)) * 1.45 + mismatchPressure + offensiveMomentum + openPlayFactor + derbyCornerPush
  ));
  const expCorners = expCornersNum.toFixed(1);
  const bestCornerOpt = selectOptimalStatLine(expCornersNum, [7.5, 8.5, 9.5], [9.5, 10.5]);
  const cornerLine = `${bestCornerOpt.label} (${bestCornerOpt.prob}%)`;

  const closeness = 1 - Math.min(1, Math.abs(pH - pA) * 1.75);
  const frustrationFactor = ((hInfo.lossesCount + aInfo.lossesCount) - 2.8) * 0.24;
  const drawFriction = ((hInfo.drawRatio + aInfo.drawRatio) / 2 - 0.25) * 1.8;
  const derbyCardPush = isDerby ? 0.70 : 0;

  const expCardsNum = Math.max(2.6, Math.min(6.4, 
    (lg.kBase || 4.3) + (closeness - 0.52) * 1.20 + frustrationFactor + drawFriction + derbyCardPush
  ));
  const expCards = expCardsNum.toFixed(1);
  const bestCardOpt = selectOptimalStatLine(expCardsNum, [3.5, 4.5], [4.5, 5.5]);
  const cardLine = `${bestCardOpt.label} (${bestCardOpt.prob}%)`;

  const actualCorners = (realHCorners !== null && realACorners !== null) ? (realHCorners + realACorners) : null;
  const actualCards = (realHYellow !== null && realAYellow !== null) ? (realHYellow + realAYellow + realHRed + realARed) : null;

  return {
    id: ev.id, league: lg.name, icon: lg.icon, cat: lg.cat, date: roDateStr(dt), time: roTimeStr(dt),
    status: stState === "post" ? "FT" : (stState === "in" ? "LIVE" : "NS"),
    home: hName, away: aName, hScore, aScore, hHT, aHT, hForm: hInfo.formDisplay, aForm: aInfo.formDisplay,
    lamH: lamH.toFixed(2), lamA: lamA.toFixed(2),
    isDerby, lowData, hasMktOdds: !!(mkt && (mkt.mktPH || mkt.ouLine)),
    edgePct: best.edgePct || 0,
    pick: best.name, mktType: best.mktType || "OTHER", prob: Math.round(best.prob * 100), odd: +best.odd.toFixed(2),
    tipsterScore: best.valueScore * (lowData ? 0.82 : 1.0),
    expCorners, cornerLine, actualCorners,
    expCards, cardLine, actualCards,
    probs: { p1: Math.round(pH*100), pX: Math.round(pD*100), p2: Math.round(pA*100), o25: Math.round(pO25*100), gg: Math.round(pGG*100), o15: Math.round(pO15*100) }
  };
}

function buildOptimalTicket(pool, targetOdd) {
  if (!pool || !pool.length) return { picks: [], totalOdd: 1.0 };
  const sorted = [...pool].sort((a, b) => b.tipsterScore - a.tipsterScore);
  const picks = [];
  const usedIds = new Set();
  const marketCounts = {};
  let tot = 1.0;

  while (picks.length < 11 && tot < targetOdd * 0.94) {
    const remainingNeeded = targetOdd / tot;
    let bestCandidate = null;
    let bestScore = -999;

    for (let m of sorted) {
      if (usedIds.has(m.id)) continue;
      const mCount = marketCounts[m.mktType] || 0;
      const diversityPenalty = mCount >= 2 ? 0.78 : (mCount === 1 ? 0.92 : 1.05);

      let targetFit = 1.0;
      if (remainingNeeded <= 2.25) {
        const dist = Math.abs(m.odd - remainingNeeded);
        targetFit = Math.max(0.5, 1.35 - dist * 0.65);
      }

      const candidateScore = m.tipsterScore * diversityPenalty * targetFit;
      if (candidateScore > bestScore) {
        bestScore = candidateScore;
        bestCandidate = m;
      }
    }

    if (!bestCandidate) break;
    picks.push(bestCandidate);
    usedIds.add(bestCandidate.id);
    marketCounts[bestCandidate.mktType] = (marketCounts[bestCandidate.mktType] || 0) + 1;
    tot *= bestCandidate.odd;
  }

  return { picks, totalOdd: tot };
}

async function loadMatchesForDate(iso) {
  renderSubBars();
  if (cacheByDate[iso]) { renderViewport(); return; }
  document.getElementById("viewport").innerHTML = `<div class="cyber-card" style="text-align:center;padding:28px;color:var(--neon-cyan);">⚡ Joe scanează clasamentele și datele xG pentru <b>${iso}</b>...</div>`;
  const ymd = iso.replace(/-/g, "");
  const res = await Promise.all(LEAGUES.map(l =>
    fetchWithTimeout(`https://site.api.espn.com/apis/site/v2/sports/soccer/${l.slug}/scoreboard?dates=${ymd}`)
      .then(d => ({ l, evs: (d && d.events) || [] }))
      .catch(() => ({ l, evs: [] }))
  ));
  const list = [];
  res.forEach(r => r.evs.forEach(ev => {
    try {
      const m = analyzeMatch(ev, r.l);
      if (m.date === iso) list.push(m);
    } catch (e) {}
  }));

  if (list.length > 0) {
    cacheByDate[iso] = list;
    try { localStorage.setItem("joe_v6_cache_" + iso, JSON.stringify(list)); } catch (e) {}
  } else {
    try {
      const backup = localStorage.getItem("joe_v6_cache_" + iso);
      cacheByDate[iso] = backup ? JSON.parse(backup) : [];
    } catch (e) { cacheByDate[iso] = []; }
  }

  autoSettleProjectBets(cacheByDate[iso]);
  renderViewport();
}

async function loadEuropaMatches() {
  renderSubBars();
  if (europaMatches.length) { renderViewport(); return; }
  document.getElementById("viewport").innerHTML = `<div class="cyber-card" style="text-align:center;padding:28px;color:var(--neon-gold);">🏆 Joe analizează cupele europene...</div>`;
  const now = new Date(), s = roDateStr(new Date(now.getTime() - 2*86400000)).replace(/-/g, ""), e = roDateStr(new Date(now.getTime() + 18*86400000)).replace(/-/g, "");
  const res = await Promise.all(LEAGUES.filter(l => l.cat === "eu").map(l =>
    fetchWithTimeout(`https://site.api.espn.com/apis/site/v2/sports/soccer/${l.slug}/scoreboard?dates=${s}-${e}`)
      .then(d => ({ l, evs: (d && d.events) || [] }))
      .catch(() => ({ l, evs: [] }))
  ));
  const list = [];
  res.forEach(r => r.evs.forEach(ev => {
    try { list.push(analyzeMatch(ev, r.l)); } catch (err) {}
  }));
  list.sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time));
  europaMatches = list;
  renderViewport();
}

async function initProject() {
  if (isSupabaseConfigured()) {
    try {
      const r = await fetch(`${SUPABASE_URL}/rest/v1/jack_project?id=eq.1&select=data`, { headers: sbHeaders() });
      if (r.ok) {
        const rows = await r.json();
        if (rows && rows.length > 0 && rows[0].data) project = rows[0].data;
      }
    } catch (e) { console.error(e); }
  }
  recalcBankroll(false);
}

async function saveToDB() {
  if (!isSupabaseConfigured()) return;
  try {
    const r = await fetch(`${SUPABASE_URL}/rest/v1/jack_project?id=eq.1`, {
      method: "PATCH",
      headers: sbHeaders(),
      body: JSON.stringify({ data: project })
    });
    document.getElementById("liveClock").innerText = r.ok ? "● Cloud Synced" : "● Sync Error";
  } catch (e) {
    document.getElementById("liveClock").innerText = "● Sync Error";
  }
}

function recalcBankroll(shouldSave = true) {
  let b = project.initial_bankroll || 500.0;
  (project.bets || []).forEach(bet => {
    if (bet.status === "WIN") b += bet.stake * (bet.odd - 1);
    else if (bet.status === "LOSS") b -= bet.stake;
  });
  project.bankroll = +b.toFixed(2);
  document.getElementById("topBankroll").innerText = project.bankroll.toFixed(2);
  if (shouldSave) saveToDB();
}

function checkBetOutcome(pick, h, a, hHT = null, aHT = null) {
  const t = h + a;
  if (pick.startsWith("1 (")) return h > a;
  if (pick.startsWith("2 (")) return a > h;
  if (pick === "1 & Peste 1.5 Goluri") return h > a && t >= 2;
  if (pick === "2 & Peste 1.5 Goluri") return a > h && t >= 2;
  if (pick.startsWith("PSF 1")) return h > a || (hHT !== null && aHT !== null && hHT > aHT);
  if (pick.startsWith("PSF 2")) return a > h || (hHT !== null && aHT !== null && aHT > hHT);
  if (pick.includes("1X & Peste 1.5")) return h >= a && t >= 2;
  if (pick.includes("X2 & Peste 1.5")) return a >= h && t >= 2;
  if (pick.includes("1X & Sub 3.5")) return h >= a && t <= 3;
  if (pick.includes("X2 & Sub 3.5")) return a >= h && t <= 3;
  if (pick.includes("Peste 2.5")) return t >= 3;
  if (pick.includes("Sub 2.5")) return t <= 2;
  if (pick.includes("Peste 1.5")) return t >= 2;
  if (pick.includes("GG")) return h > 0 && a > 0;
  if (pick.includes("1X")) return h >= a;
  if (pick.includes("X2")) return a >= h;
  return null;
}

function autoSettleProjectBets(list) {
  let ch = false;
  (project.bets || []).forEach(b => {
    if (b.status !== "PENDING") return;
    const f = list.find(m => String(m.id) === String(b.matchId) && m.status === "FT");
    if (f && f.hScore !== null) {
      const w = checkBetOutcome(b.pick, f.hScore, f.aScore, f.hHT, f.aHT);
      if (w !== null) { b.status = w ? "WIN" : "LOSS"; b.score = `${f.hScore}-${f.aScore}`; ch = true; }
    }
  });
  if (ch) recalcBankroll(true);
}

function addMatchToProject(matchId) {
  if (!hasJoeAccess()) return;
  const all = [...(cacheByDate[selectedDate] || []), ...europaMatches];
  const m = all.find(x => String(x.id) === String(matchId));
  if (!m) return;
  if (!project.bets.some(b => String(b.matchId) === String(m.id))) {
    const smart = calculateSmartStake(project.bankroll, m);
    project.bets.unshift({ id: Date.now(), matchId: m.id, date: m.date, match: `${m.home} vs ${m.away}`, league: m.league, pick: m.pick, odd: m.odd, stake: smart.stake, status: "PENDING", score: "" });
    recalcBankroll(true);
  }
  switchNav("proiect");
}

function copyMatchById(matchId) {
  const all = [...(cacheByDate[selectedDate] || []), ...europaMatches];
  const m = all.find(x => String(x.id) === String(matchId));
  if (!m) return;
  copyText(`${m.home} vs ${m.away} — ${m.pick} (@${m.odd.toFixed(2)})`);
}

function editBetDetails(id) {
  const b = project.bets.find(x => x.id === id);
  if (!b) return;
  const o = parseFloat(prompt(`Cotă nouă pentru ${b.match}:`, b.odd));
  if (isNaN(o) || o <= 1.01) return;
  const s = parseFloat(prompt("Miză nouă (RON):", b.stake));
  if (isNaN(s) || s <= 0) return;
  b.odd = +o.toFixed(2); b.stake = +s.toFixed(2);
  recalcBankroll(true); renderViewport();
}

function updateBetStatus(id, st) {
  const b = project.bets.find(x => x.id === id);
  if (b) { b.status = st; recalcBankroll(true); renderViewport(); }
}

function deleteBet(id) {
  if (!confirm("Ștergi acest pariu?")) return;
  project.bets = project.bets.filter(x => x.id !== id);
  recalcBankroll(true); renderViewport();
}

function toggleDrawer(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = el.style.display === "block" ? "none" : "block";
}
