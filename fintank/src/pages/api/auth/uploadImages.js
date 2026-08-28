/* eslint-disable import/no-anonymous-default-export */
const AWS = require('aws-sdk');
import { nanoid } from 'nanoid';



const awsConfig = {
    accessKeyId:`${process.env.NEXT_PUBLIC_AWS_ACCESS_KEY_ID}`,
    secretAccessKey:`${process.env.NEXT_PUBLIC_AWS_SECRET_ACESS_KEY}`,
    region: `${process.env.NEXT_PUBLIC_AWS_REGION}`,
    apiVersion:`${process.env.NEXT_PUBLIC_AWS_VERSION}`
};

const S3 = new AWS.S3(awsConfig);

export default async(req, res) => {
    try{
        const {image} = req.body
        if(!image){
            return res.status(400).send("No Image Selected")
        }

        const base64Data = new Buffer.from(image.replace(/^data:image\/\w+;base64,/, ''), "base64");

        const type = image.split(';')[0].split("/")[1]

        const params = {
            Bucket:"thetradingfloor",
            Key:`${nanoid()}.${type}`,
            Body:base64Data,
            ACL:'public-read',
            ContentEncoding:"base64",
            ContentType:`image/${type}`,
        }

        S3.upload(params, (err, data) => {
            if(err){
                console.log(err)
                return res.sendStatus(400);
            }
            console.log(data)
            res.send(data)
        })
    } catch(err){
        console.log(err)
    }
}