import econImages from "@data/econ.json"
import energyImages from "@data/energy.json"
import hcImages from "@data/health-care.json"
import marketImages from "@data/markets.json"
import materialImages from "@data/material.json"
import techImages from "@data/technology.json"
import commodityImages from "@data/commodities.json"
import consumerImages from "@data/consumer.json"
import conflictImages from "@data/conflict.json"
import industrialsImages from "@data/industrials.json"
import financeImages from "@data/finance.json"
import extraImages from "@data/home-images.json";
import politicImages from "@data/politic.json";
import usImages from "@data/us.json";
import russiaImages from "@data/russia.json";
import midEastImages from "@data/mideast.json";
import japanImages from "@data/japan.json";
import cnImages from "@data/china.json";
import communicationImages from "@data/communications.json";
import alemanImages from "@data/aleman.json";
import africaImages from "@data/africa.json";
import latamImages from "@data/latam.json";
import commodImages from "@data/commodities.json";
import cryptoImages from "@data/crypto.json";


const imagesForConsumers = consumerImages.consumerImages.concat(econImages.econImages[2]);
const imagesForMaterials = materialImages.marketImages.concat(commodityImages.commodityImages[7], commodityImages.commodityImages[4])
const imagesForTechnology = techImages.techImages;
const imagesForFinance = financeImages.financeImages.concat(consumerImages.consumerImages[1], marketImages.marketImages[6], marketImages.marketImages[7]);
const imagesForEconomy = econImages.econImages.concat(extraImages.extraImages);
const imagesforMarkets = marketImages.marketImages.concat(extraImages.extraImages);
const imagesForPolitics = politicImages.polImages;
const imagesForWar = conflictImages.conflictImages;
const imagesForHealthCare = hcImages.hcImages;
const imagesForUS = usImages.usImages;
const imagesForChina = cnImages.chinaImages;
const imagesForCommunications = communicationImages.communicationsImages;
const imagesForMiddleEast = midEastImages.mideastImages;
const imagesForAfrica = africaImages.africaImages;
const imagesForLatam = latamImages.latamImages;
const imagesForRussia = russiaImages.russiaImages;
const imagesForAleman = alemanImages.alemanImages;
const imagesForIndus = industrialsImages.industrialsImages;
const imagesForJapan = japanImages.japonImages;
const imagesForEnergy = energyImages.energyImages;
const imagesForComodities = commodImages.commodityImages;
const imagesForCrypto = cryptoImages.cryptoImages;



export const selectImages= (newsType) => {

    //first param is passed into the funtion i.e. URL
    //econd param is function that calls the param
    let images;


        switch(newsType){
            case "global_news":
                images= imagesforMarkets
                break;
            case "econ":
                images = imagesForEconomy
                break;
            case "politics":
                images = imagesForPolitics
                break;
            case "macro":
                images = imagesForEconomy
                break;
            case "war":
                images = imagesForWar
                break;
            case "us_stock":
                images = imagesForUS
                break;
            case "china_stock":
                images = imagesForChina
                break;
            case "utilities":
                images = imagesForRussia
                break;
            case "canadian_stock":
                images = imagesForMiddleEast
                break;
            case "eu_markets":
                images = imagesForAleman
                break;
            case "japan_stock":
                images = imagesForJapan
                break;
            case "africa_economy":
                images = imagesForAfrica
                break;
            case "south_america":
                images = imagesForLatam
                break;
            case "tech":
                images = imagesForTechnology
                break;
            case "energy":
                images = imagesForEnergy
                break;
            case "pharmaceuticals":
                images = imagesForHealthCare
                break;
            case "financials":
                images = imagesForFinance
                break;
            case "consumer_trends":
                images = imagesForConsumers
                break;
            case "basic_materials":
                images = imagesForMaterials
                break;
            case "real_estate":
                images = imagesForCommunications
                break;
            case "communications":
                images = imagesForCommunications
                break;
            case "industrials":
                images = imagesForIndus
                break;
            case "oil":
                images = imagesForComodities
                break;
            case "crypto":
                images = imagesForCrypto
                break;
            case "digital_assets":
                images = imagesForCrypto
                break;
            default:
                break
    }

    return images

}