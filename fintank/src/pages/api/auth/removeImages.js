const AWS = require('aws-sdk');



const awsConfig = {
    accessKeyId:`${process.env.NEXT_PUBLIC_AWS_ACCESS_KEY_ID}`,
    secretAccessKey:`${process.env.NEXT_PUBLIC_AWS_SECRET_ACESS_KEY}`,
    region: `${process.env.NEXT_PUBLIC_AWS_REGION}`,
    apiVersion:`${process.env.NEXT_PUBLIC_AWS_VERSION}`
};

const S3 = new AWS.S3(awsConfig);


// eslint-disable-next-line import/no-anonymous-default-export
export default async(req, res) => {
    try{
        const {imageKey} = req.body;
        const params ={
            Bucket:"thetradingfloor",
            Key: imageKey,
        }
        //send req to s3

        S3.deleteObject(params, (err, data) => {
            if(err){
                console.log(err)
                res.sendStatus(400);
            }

            res.send({ok:true});
        })
    }catch(err){
        console.log(err)
    }
}